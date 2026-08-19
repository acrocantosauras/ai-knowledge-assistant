"""Tests for QA streaming endpoint."""

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


def test_qa_stream_requires_authentication() -> None:
    """Streaming endpoint requires authentication."""
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/qa/ask/stream",
        json={"question": "What is AI?"},
    )
    assert response.status_code in (401, 422)


# --- Streaming ---


def test_qa_stream_creates_conversation_and_streams_answer() -> None:
    """Streaming Q&A creates a new conversation and returns SSE events."""
    client = TestClient(create_app())
    token = _register_and_login(client, "qa-stream-new@example.com")

    response = client.post(
        "/api/v1/qa/ask/stream",
        json={"question": "What is the capital of France?"},
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

    # Should have answer events
    answer_events = [e for e in events if e.get("type") == "answer"]
    assert len(answer_events) >= 1

    # All events must be valid JSON (not raw dicts)
    for event in events:
        assert isinstance(event, dict)
        assert "type" in event


def test_qa_stream_with_existing_conversation() -> None:
    """Streaming Q&A with existing conversation persists messages."""
    client = TestClient(create_app())
    token = _register_and_login(client, "qa-stream-conv@example.com")

    # Create conversation first
    conv_resp = client.post(
        "/api/v1/conversations/",
        json={"title": "Stream Test"},
        headers=_auth(token),
    )
    assert conv_resp.status_code == 201
    conversation_id = conv_resp.json()["id"]

    response = client.post(
        "/api/v1/qa/ask/stream",
        json={
            "question": "What is Python?",
            "conversation_id": conversation_id,
        },
        headers=_auth(token),
    )

    assert response.status_code == 200

    # Parse SSE events
    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    answer_events = [e for e in events if e.get("type") == "answer"]
    assert len(answer_events) >= 1

    # Verify conversation has messages
    conv_resp = client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    )
    conv_data = conv_resp.json()
    assert conv_data["message_count"] >= 2  # user + assistant


def test_qa_stream_invalid_conversation() -> None:
    """Streaming Q&A with non-existent conversation returns error event."""
    client = TestClient(create_app())
    token = _register_and_login(client, "qa-stream-invalid@example.com")

    response = client.post(
        "/api/v1/qa/ask/stream",
        json={
            "question": "What is AI?",
            "conversation_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=_auth(token),
    )

    assert response.status_code == 200

    # Should have an error event
    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) >= 1
    assert "not found" in error_events[0]["error"].lower()


def test_qa_stream_no_documents_returns_friendly_answer() -> None:
    """Streaming Q&A with no documents returns a friendly message."""
    client = TestClient(create_app())
    token = _register_and_login(client, "qa-stream-nodocs@example.com")

    response = client.post(
        "/api/v1/qa/ask/stream",
        json={"question": "What is quantum computing?"},
        headers=_auth(token),
    )

    assert response.status_code == 200

    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    answer_events = [e for e in events if e.get("type") == "answer"]
    assert len(answer_events) >= 1
    # The last answer event should be final
    assert answer_events[-1]["is_final"] is True
    # Should contain a message about no documents
    full_answer = "".join(e.get("content", "") for e in answer_events)
    lower_answer = full_answer.lower()
    assert "relevant documents" in lower_answer or "upload" in lower_answer


def test_qa_stream_cross_user_isolation() -> None:
    """User B cannot use User A's conversation in streaming Q&A."""
    client = TestClient(create_app())

    token_a = _register_and_login(client, "qa-stream-iso-a@example.com")
    token_b = _register_and_login(client, "qa-stream-iso-b@example.com")

    # User A creates conversation
    conv_resp = client.post(
        "/api/v1/conversations/",
        json={"title": "User A's Conv"},
        headers=_auth(token_a),
    )
    conv_id = conv_resp.json()["id"]

    # User B tries to use it
    response = client.post(
        "/api/v1/qa/ask/stream",
        json={
            "question": "Hello",
            "conversation_id": conv_id,
        },
        headers=_auth(token_b),
    )

    assert response.status_code == 200

    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) >= 1
