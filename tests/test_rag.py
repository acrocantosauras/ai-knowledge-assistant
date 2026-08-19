"""Tests for RAG API endpoints."""

import json

from fastapi.testclient import TestClient

from app.main import create_app


def _register_and_login(
    client: TestClient,
    email: str,
    password: str = "TestPassword123!",
) -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": email.split("@")[0],
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Authentication ---


def test_rag_search_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/rag/search",
        json={"query": "test query"},
    )
    assert response.status_code in (401, 422)


def test_rag_ask_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/rag/ask",
        json={"question": "What is this about?"},
    )
    assert response.status_code in (401, 422)


def test_rag_stream_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/rag/ask/stream",
        json={"question": "What is this about?"},
    )
    assert response.status_code in (401, 422)


# --- Search ---


def test_rag_search_empty_query() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "rag-empty@example.com")

    response = client.post(
        "/api/v1/rag/search",
        json={"query": ""},
        headers=_auth(token),
    )
    assert response.status_code == 422


def test_rag_search_no_documents() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "rag-none@example.com")

    response = client.post(
        "/api/v1/rag/search",
        json={"query": "test query"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "test query"
    assert data["results"] == []
    assert data["total"] == 0


def test_rag_search_with_documents() -> None:
    """Search returns matching chunks after document upload."""
    client = TestClient(create_app())
    token = _register_and_login(client, "rag-search-doc@example.com")

    # Upload a document with known content
    client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "facts.txt",
                b"The capital of France is Paris."
                b" It is known for the Eiffel Tower.",
                "text/plain",
            )
        },
        headers=_auth(token),
    )

    response = client.post(
        "/api/v1/rag/search",
        json={"query": "capital of France"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    # Should find the chunk containing "Paris"
    contents = " ".join(r["content"] for r in data["results"])
    assert "Paris" in contents or "France" in contents


# --- Ask ---


def test_rag_ask_no_documents() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "rag-ask-none@example.com")

    response = client.post(
        "/api/v1/rag/ask",
        json={"question": "What is AI?"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert data["sources"] == []
    assert data["provider"]


def test_rag_ask_empty_question() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "rag-ask-empty@example.com")

    response = client.post(
        "/api/v1/rag/ask",
        json={"question": ""},
        headers=_auth(token),
    )
    assert response.status_code == 422


def test_rag_ask_with_documents() -> None:
    """Ask returns an answer grounded in uploaded documents."""
    client = TestClient(create_app())
    token = _register_and_login(client, "rag-ask-doc@example.com")

    client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "knowledge.txt",
                b"The sky is blue."
                b" Grass is green. The sun is yellow.",
                "text/plain",
            )
        },
        headers=_auth(token),
    )

    response = client.post(
        "/api/v1/rag/ask",
        json={"question": "What color is the sky?"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["answer"]) > 0


# --- Streaming ---


def test_rag_stream_no_documents() -> None:
    """Streaming with no documents returns a valid SSE answer event."""
    client = TestClient(create_app())
    token = _register_and_login(client, "rag-stream-none@example.com")

    response = client.post(
        "/api/v1/rag/ask/stream",
        json={"question": "What is AI?"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    # Parse SSE events
    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    assert len(events) >= 1
    # Should have an answer event
    answer_events = [e for e in events if e.get("type") == "answer"]
    assert len(answer_events) >= 1
    assert answer_events[0]["is_final"] is True
    assert "answer" in answer_events[0]["content"]


def test_rag_stream_with_documents() -> None:
    """Streaming with documents returns answer events."""
    client = TestClient(create_app())
    token = _register_and_login(client, "rag-stream-doc@example.com")

    client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "facts.txt",
                b"The capital of France is Paris."
                b" It is known for the Eiffel Tower.",
                "text/plain",
            )
        },
        headers=_auth(token),
    )

    response = client.post(
        "/api/v1/rag/ask/stream",
        json={"question": "What is the capital of France?"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    # Should have at least answer events
    answer_events = [e for e in events if e.get("type") == "answer"]
    assert len(answer_events) >= 1
    # Last answer event should be final
    assert answer_events[-1]["is_final"] is True
    # All events must be valid JSON (not raw dicts)
    for event in events:
        assert isinstance(event, dict)
        assert "type" in event


# --- Embedding filtering regression ---


def test_text_search_fallback_with_mock_embeddings() -> None:
    """With mock provider, search uses text fallback, not vector search."""
    client = TestClient(create_app())
    token = _register_and_login(client, "rag-mock-fallback@example.com")

    # Upload a document
    client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "science.txt",
                b"Quantum computing uses qubits.",
                "text/plain",
            )
        },
        headers=_auth(token),
    )

    # With mock provider, search should use text fallback
    resp = client.post(
        "/api/v1/rag/search",
        json={"query": "quantum", "limit": 5},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_user_isolation_in_text_search() -> None:
    """Text search fallback respects user isolation."""
    client = TestClient(create_app())
    token_a = _register_and_login(client, "text-iso-a@example.com")
    token_b = _register_and_login(client, "text-iso-b@example.com")

    # User A uploads
    client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "secret.txt",
                b"Top secret project Alpha",
                "text/plain",
            )
        },
        headers=_auth(token_a),
    )

    # User B searches - should not find User A's content
    resp = client.post(
        "/api/v1/rag/search",
        json={"query": "project Alpha"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# --- Cross-user isolation ---


def test_rag_search_cross_user_isolation() -> None:
    """User B cannot search User A's documents."""
    client = TestClient(create_app())

    token_a = _register_and_login(client, "rag-iso-a@example.com")
    token_b = _register_and_login(client, "rag-iso-b@example.com")

    # User A uploads
    client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "secret.txt",
                b"Top secret project Phoenix launch"
                b" date is December 2025.",
                "text/plain",
            )
        },
        headers=_auth(token_a),
    )

    # User B searches — should find nothing
    resp = client.post(
        "/api/v1/rag/search",
        json={"query": "project Phoenix"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # User B asks — should get no-sources answer
    resp = client.post(
        "/api/v1/rag/ask",
        json={"question": "When is project Phoenix launching?"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["sources"] == []
