"""Metrics access control, OpenAI error translation and SSE/citation tests."""

import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.services import llm as llm_module
from app.services.provider_errors import ProviderError, translate_openai_error
from app.services.rag import EmbeddingService

TOKEN = "metrics-token-0123456789"


# --- Metrics protection -----------------------------------------------------


@pytest.fixture
def metrics_client(monkeypatch):
    monkeypatch.setenv("APP_METRICS_TOKEN", TOKEN)
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    monkeypatch.delenv("APP_METRICS_TOKEN")
    get_settings.cache_clear()


def test_metrics_denied_without_token(metrics_client) -> None:
    assert metrics_client.get("/metrics").status_code == 401


def test_metrics_denied_with_wrong_token(metrics_client) -> None:
    resp = metrics_client.get("/metrics", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401
    resp = metrics_client.get("/metrics", headers={"Authorization": f"Basic {TOKEN}"})
    assert resp.status_code == 401


def test_metrics_allowed_with_token(metrics_client) -> None:
    resp = metrics_client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text


def test_health_endpoints_stay_open_when_metrics_protected(metrics_client) -> None:
    assert metrics_client.get("/health").status_code == 200
    assert metrics_client.get("/health/ready").status_code == 200


def test_production_requires_metrics_token() -> None:
    from pydantic import ValidationError

    from app.config import Settings

    base = {
        "environment": "production",
        "jwt_secret_key": "x" * 48,
        "database_url": "postgresql+asyncpg://u:Str0ngPw@postgres:5432/db",
    }
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **base)
    assert Settings(_env_file=None, metrics_token="m" * 20, **base)


# --- OpenAI error translation (simulated SDK errors, NOT a real-provider test) ---


def _resp(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://x"))


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (
            openai.AuthenticationError(
                "bad key sk-SECRET", response=_resp(401), body=None
            ),
            502,
        ),
        (openai.RateLimitError("quota sk-SECRET", response=_resp(429), body=None), 429),
        (openai.APITimeoutError(request=httpx.Request("POST", "https://x")), 504),
        (openai.InternalServerError("boom", response=_resp(500), body=None), 502),
    ],
)
def test_translate_openai_errors(exc, status) -> None:
    err = translate_openai_error(exc)
    assert isinstance(err, ProviderError)
    assert err.status_code == status
    assert "sk-" not in err.public_detail


def test_translate_ignores_unrelated_errors() -> None:
    assert translate_openai_error(ValueError("x")) is None


def _failing_client(exc):
    async def create(*a, **k):
        raise exc

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        embeddings=SimpleNamespace(create=create),
    )


@pytest.mark.asyncio
async def test_llm_provider_translates_auth_error(monkeypatch) -> None:
    monkeypatch.setenv("APP_OPENAI_API_KEY", "sk-test-not-real")
    get_settings.cache_clear()
    exc = openai.AuthenticationError("x", response=_resp(401), body=None)
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **k: _failing_client(exc))
    provider = llm_module.OpenAIProvider()
    with pytest.raises(ProviderError) as info:
        await provider.generate("hi")
    assert info.value.status_code == 502
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_embeddings_translate_rate_limit_and_dimension(monkeypatch) -> None:
    monkeypatch.setenv("APP_OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("APP_EMBEDDING_PROVIDER", "openai")
    get_settings.cache_clear()
    exc = openai.RateLimitError("x", response=_resp(429), body=None)
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **k: _failing_client(exc))
    with pytest.raises(ProviderError) as info:
        await EmbeddingService().generate_embeddings(["a"])
    assert info.value.status_code == 429

    async def short(*a, **k):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])

    monkeypatch.setattr(
        openai,
        "AsyncOpenAI",
        lambda **k: SimpleNamespace(embeddings=SimpleNamespace(create=short)),
    )
    with pytest.raises(ProviderError) as info:
        await EmbeddingService().generate_embeddings(["a"])
    assert "dimension" in info.value.public_detail
    get_settings.cache_clear()


# --- Streaming SSE and citations (mock provider) ------------------------------


def _auth(client: TestClient) -> dict[str, str]:
    creds = {"email": "sse@example.com", "password": "TestPassword123!"}
    client.post("/api/v1/auth/register", json={**creds, "display_name": "s"})
    tok = client.post("/api/v1/auth/login", json=creds).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _events(text: str) -> list[dict]:
    frames = [f for f in text.split("\n\n") if f.strip()]
    out = []
    for frame in frames:
        assert frame.startswith("data: "), frame
        out.append(json.loads(frame[len("data: ") :]))
    return out


def test_stream_event_order_sources_chunks_final_and_persisted_citations(
    client: TestClient,
) -> None:
    h = _auth(client)
    up = client.post(
        "/api/v1/documents/upload",
        headers=h,
        files={"file": ("fr.txt", b"The capital of France is Paris.", "text/plain")},
    )
    assert up.status_code == 201
    doc_id = up.json()["id"]

    resp = client.post(
        "/api/v1/qa/ask/stream", headers=h, json={"question": "capital of France"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"
    events = _events(resp.text)

    assert events[0]["type"] == "sources"
    src = events[0]["sources"][0]
    assert src["document_id"] == doc_id
    assert "Paris" in src["content_preview"]
    assert src["chunk_id"]

    answers = [e for e in events if e["type"] == "answer"]
    assert answers, "no answer chunks"
    assert [e["is_final"] for e in answers][-1] is True
    assert not any(e["is_final"] for e in answers[:-1])
    assert "".join(e["content"] or "" for e in answers).strip()
    assert not [e for e in events if e["type"] == "error"]

    # Citations are persisted on the assistant message
    convs = client.get("/api/v1/conversations/", headers=h).json()
    conv_id = (convs.get("conversations") or convs.get("items"))[0]["id"]
    detail = client.get(f"/api/v1/conversations/{conv_id}", headers=h).json()
    assistant = [m for m in detail["messages"] if m["role"] == "assistant"][0]
    meta = assistant.get("metadata") or assistant.get("message_metadata") or {}
    assert meta["sources"][0]["document_id"] == doc_id


def test_stream_error_event_for_unknown_conversation(client: TestClient) -> None:
    h = _auth(client)
    resp = client.post(
        "/api/v1/qa/ask/stream",
        headers=h,
        json={
            "question": "x?",
            "conversation_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    events = _events(resp.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["error"] == "Conversation not found"


def test_stream_provider_failure_emits_sanitized_error_event(
    client: TestClient, monkeypatch
) -> None:
    h = _auth(client)

    async def boom(*a, **k):
        raise RuntimeError("secret internal detail sk-LEAK")
        yield  # pragma: no cover

    monkeypatch.setattr("app.api.routes.qa.ask_question_stream", boom)
    resp = client.post("/api/v1/qa/ask/stream", headers=h, json={"question": "q?"})
    assert resp.status_code == 200
    events = _events(resp.text)
    assert events[-1]["type"] == "error"
    assert "sk-LEAK" not in resp.text and "secret" not in resp.text


def test_client_disconnect_mid_stream_is_safe(client: TestClient) -> None:
    h = _auth(client)
    with client.stream(
        "POST", "/api/v1/qa/ask/stream", headers=h, json={"question": "hello"}
    ) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                break  # drop the connection after the first event
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/conversations/", headers=h).status_code == 200
