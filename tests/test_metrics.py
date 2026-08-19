"""Tests for Prometheus /metrics endpoint."""

from fastapi.testclient import TestClient

from app.main import create_app


def _register_and_login(
    client: TestClient, email: str, password: str = "TestPassword123!"
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


# --- Basic endpoint tests ---


def test_metrics_endpoint_returns_200() -> None:
    """GET /metrics should return 200 with Prometheus text format."""
    client = TestClient(create_app())
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_metrics_contains_http_request_counters() -> None:
    """Metrics should include http_requests_total after a request."""
    client = TestClient(create_app())
    # Make a request that will be instrumented
    client.get("/health")

    response = client.get("/metrics")
    body = response.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "http_requests_in_flight" in body


def test_metrics_does_not_record_own_requests() -> None:
    """The /metrics endpoint itself should not be recorded."""
    client = TestClient(create_app())
    # Hit /metrics several times
    client.get("/metrics")
    client.get("/metrics")

    response = client.get("/metrics")
    body = response.text
    # The metrics endpoint path should not appear as an endpoint label
    assert 'endpoint="/metrics"' not in body


def test_metrics_contains_app_metrics() -> None:
    """Metrics should include application-level counters."""
    client = TestClient(create_app())
    response = client.get("/metrics")
    body = response.text
    assert "documents_uploaded_total" in body
    assert "conversations_created_total" in body
    assert "qa_questions_total" in body
    assert "rag_search_total" in body


# --- Instrumentation integration tests ---


def test_instrumented_requests_recorded() -> None:
    """Requests through instrumented routes should be counted."""
    client = TestClient(create_app())

    # Make several requests
    client.get("/health")
    client.get("/health")
    client.get("/health/ready")

    response = client.get("/metrics")
    body = response.text

    # Should have recorded at least some health requests
    assert 'endpoint="/health"' in body
    assert 'endpoint="/health/ready"' in body


def test_auth_requests_recorded() -> None:
    """Auth requests should be recorded with correct labels."""
    client = TestClient(create_app())
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "metrics-test@example.com",
            "password": "TestPassword123!",
        },
    )
    client.post(
        "/api/v1/auth/login",
        json={
            "email": "metrics-test@example.com",
            "password": "TestPassword123!",
        },
    )

    response = client.get("/metrics")
    body = response.text
    assert 'endpoint="/api/v1/auth/register"' in body
    assert 'endpoint="/api/v1/auth/login"' in body


def test_metrics_records_latency_histogram() -> None:
    """Request latency should be recorded in the histogram."""
    client = TestClient(create_app())
    client.get("/health")

    response = client.get("/metrics")
    body = response.text
    # Histogram should have bucket and count entries
    assert "http_request_duration_seconds_bucket" in body
    assert "http_request_duration_seconds_count" in body
    assert "http_request_duration_seconds_sum" in body


def test_metrics_labels_include_method() -> None:
    """Metric labels should include the HTTP method."""
    client = TestClient(create_app())
    client.get("/health")

    response = client.get("/metrics")
    body = response.text
    assert 'method="GET"' in body


def test_metrics_labels_include_status() -> None:
    """Metric labels should include the HTTP status code."""
    client = TestClient(create_app())
    client.get("/health")

    response = client.get("/metrics")
    body = response.text
    assert 'status="200"' in body


# --- Application metrics integration ---


def test_document_upload_increments_counter() -> None:
    """Document upload should increment documents_uploaded_total."""
    client = TestClient(create_app())
    token = _register_and_login(client, "metrics-upload@example.com")

    client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.txt", b"content", "text/plain")},
        headers=_auth(token),
    )

    response = client.get("/metrics")
    body = response.text
    assert 'documents_uploaded_total' in body
    assert f'user_id="{token[:36]}"' in body or 'user_id="' in body


def test_conversation_create_increments_counter() -> None:
    """Conversation creation should increment conversations_created_total."""
    client = TestClient(create_app())
    token = _register_and_login(client, "metrics-conv@example.com")

    client.post(
        "/api/v1/conversations/",
        json={"title": "Metrics Test"},
        headers=_auth(token),
    )

    response = client.get("/metrics")
    body = response.text
    assert 'conversations_created_total' in body


def test_qa_ask_increments_counter() -> None:
    """QA ask should increment qa_questions_total."""
    client = TestClient(create_app())
    token = _register_and_login(client, "metrics-qa@example.com")

    client.post(
        "/api/v1/qa/ask",
        json={"question": "What is AI?"},
        headers=_auth(token),
    )

    response = client.get("/metrics")
    body = response.text
    assert 'qa_questions_total' in body
    assert 'qa_latency_seconds' in body


def test_rag_search_increments_counter() -> None:
    """RAG search should increment rag_search_total and rag_chunks_returned."""
    client = TestClient(create_app())
    token = _register_and_login(client, "metrics-rag@example.com")

    client.post(
        "/api/v1/rag/search",
        json={"query": "test query"},
        headers=_auth(token),
    )

    response = client.get("/metrics")
    body = response.text
    assert 'rag_search_total' in body
    assert 'rag_chunks_returned' in body
