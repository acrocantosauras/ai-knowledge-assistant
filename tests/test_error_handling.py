"""Tests for error handling, sanitization, and operational readiness."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# --- Readiness probe error sanitization ---


def test_readiness_does_not_leak_database_connection_string() -> None:
    """Readiness probe must never expose raw exception details that may
    contain connection strings, hostnames, or credentials."""
    from unittest.mock import AsyncMock

    from app.api.dependencies import get_db_session
    from app.main import create_app

    # Create a mock session whose execute() raises with credential details
    mock_session = AsyncMock()
    mock_session.execute.side_effect = ConnectionError(
        "could not connect to server: Connection refused "
        "127.0.0.1:5432 — password: s3cret"
    )

    async def _yield_mock():  # type: ignore[return]
        yield mock_session  # type: ignore[misc]

    app = create_app()
    app.dependency_overrides[get_db_session] = _yield_mock

    client = TestClient(app)
    resp = client.get("/health/ready")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    db_check = data["checks"]["database"]
    # Must NOT contain the raw exception text
    assert "s3cret" not in db_check
    assert "Connection refused" not in db_check
    assert "127.0.0.1" not in db_check
    # Must indicate failure without leaking details
    assert "error" in db_check.lower()

    # Cleanup
    app.dependency_overrides.clear()


def test_readiness_ok_when_database_is_healthy() -> None:
    """Readiness probe returns 200 when database is reachable."""
    client = TestClient(create_app())
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["checks"]["database"] == "ok"


# --- Global exception handler ---


def test_unhandled_exception_returns_500_not_stack_trace() -> None:
    """Unexpected server errors must return a generic message, not a
    full stack trace or internal detail."""
    from fastapi import APIRouter

    app = create_app()
    test_router = APIRouter(prefix="/api/v1/test-error")

    @test_router.get("/boom")
    async def _boom():
        raise RuntimeError("internal secret details: postgres://user:pass@host/db")

    app.include_router(test_router)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/v1/test-error/boom")
    assert resp.status_code == 500
    data = resp.json()
    assert data["detail"] == "Internal server error"
    # Must NOT contain the raw exception message
    assert "postgres://" not in resp.text
    assert "pass@host" not in resp.text

    app.dependency_overrides.clear()


# --- Metrics endpoint safety ---


def test_metrics_endpoint_does_not_expose_secrets() -> None:
    """The /metrics endpoint must not contain any secrets, passwords,
    API keys, or user PII."""
    client = TestClient(create_app())
    # Generate some traffic
    client.get("/health")
    client.get("/health/ready")

    resp = client.get("/metrics")
    body = resp.text

    # No secrets should appear
    assert "change-me-to-a-random-secret-key" not in body
    assert "ai_knowledge_password" not in body
    assert "password" not in body.lower() or "password_hash" not in body


# --- Health endpoint safety ---


def test_health_endpoint_does_not_expose_credentials() -> None:
    """The /health endpoint must not expose credentials or internal config."""
    client = TestClient(create_app())
    resp = client.get("/health")
    body = resp.text

    assert "password" not in body.lower()
    assert "secret" not in body.lower()
    assert "api_key" not in body.lower()
    assert "redis" not in body.lower()


def test_readiness_does_not_leak_redis_error_details() -> None:
    """Readiness probe must not expose raw Redis error details.

    Redis errors may contain hostnames, ports, or connection details.
    The client-facing response should only say "error: connection failed".
    """
    import app.core.redis as redis_mod
    from app.main import create_app

    original_settings = redis_mod.get_settings
    original_client = redis_mod._redis_client
    redis_mod.get_settings = lambda: Settings(
        redis_url="redis://localhost:19999/0",
        environment="development",
    )
    redis_mod._redis_client = None
    try:
        client = TestClient(create_app())
        resp = client.get("/health/ready")
        data = resp.json()
        redis_check = str(data["checks"].get("redis", ""))
        # Must not contain hostnames, ports, or connection details
        assert "localhost" not in redis_check
        assert "19999" not in redis_check
        assert "redis://" not in redis_check
        assert "error" in redis_check.lower()
    finally:
        redis_mod.get_settings = original_settings
        redis_mod._redis_client = original_client


# --- LLM failure behavior ---


class TestLLMFailureBehavior:
    """Test that LLM failures are handled gracefully."""

    def test_missing_openai_key_raises_runtime_error(self) -> None:
        """OpenAI provider raises RuntimeError when API key is missing
        or the openai package is not installed."""
        import app.services.llm as llm_mod
        from app.services.llm import OpenAIProvider

        llm_mod._llm_service = None
        settings = Settings(llm_provider="openai", openai_api_key="")
        provider = OpenAIProvider()
        provider.settings = settings

        with pytest.raises(RuntimeError):
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    provider.generate("test prompt")
                )
            finally:
                loop.close()

    def test_unsupported_provider_raises_value_error(self) -> None:
        """LLMService raises ValueError for unsupported provider."""
        from app.services.llm import LLMService

        service = LLMService()
        original = service.settings
        # Temporarily monkeypatch to test the branch
        import types

        bad_settings = types.SimpleNamespace(llm_provider="invalid")
        service.settings = bad_settings  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Unsupported"):
            service._create_provider()
        service.settings = original

    def test_mock_provider_always_works(self) -> None:
        """Mock provider should never fail."""
        import asyncio

        from app.services.llm import MockProvider

        provider = MockProvider()
        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(
                provider.generate("test prompt")
            )
        finally:
            loop.close()
        assert response.content
        assert response.provider == "mock"
