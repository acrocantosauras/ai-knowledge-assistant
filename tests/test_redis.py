"""Tests for Redis client and health check integration."""

import pytest

from app.config import Settings
from app.core.redis import check_redis_health, is_redis_configured


def test_is_redis_configured_false_by_default() -> None:
    """Redis should not be configured when redis_url is empty."""
    assert is_redis_configured() is False


def test_is_redis_configured_true_when_url_set() -> None:
    """Redis should be detected as configured when redis_url is set."""
    import app.core.redis as redis_mod

    original = redis_mod.get_settings
    redis_mod.get_settings = lambda: Settings(
        redis_url="redis://localhost:6379/0"
    )
    try:
        assert is_redis_configured() is True
    finally:
        redis_mod.get_settings = original


@pytest.mark.asyncio
async def test_check_redis_health_skipped_when_not_configured() -> None:
    """Health check should return skipped when Redis is not configured."""
    result = await check_redis_health()
    assert result == {"status": "skipped"}


@pytest.mark.asyncio
async def test_check_redis_health_error_when_unreachable() -> None:
    """Health check should return error when Redis URL points nowhere."""
    import app.core.redis as redis_mod
    original_settings = redis_mod.get_settings
    redis_mod.get_settings = lambda: Settings(
        redis_url="redis://localhost:19999/0"
    )
    # Reset singleton so it picks up the new settings
    original_client = redis_mod._redis_client
    redis_mod._redis_client = None
    try:
        result = await check_redis_health()
        # Should be error since nothing is listening on port 19999
        assert result["status"] == "error"
        assert "error" in result
    finally:
        redis_mod.get_settings = original_settings
        redis_mod._redis_client = original_client


def test_readiness_probe_includes_redis_when_configured() -> None:
    """Readiness probe should include Redis in checks when configured."""
    from fastapi.testclient import TestClient

    import app.core.redis as redis_mod
    from app.main import create_app

    original_settings = redis_mod.get_settings
    redis_mod.get_settings = lambda: Settings(
        redis_url="redis://localhost:19999/0",
        environment="development",
    )
    redis_mod._redis_client = None
    try:
        client = TestClient(create_app())
        response = client.get("/health/ready")
        # Should return 503 since Redis is unreachable
        assert response.status_code == 503
        data = response.json()
        assert "redis" in data["checks"]
        assert data["checks"]["redis"].startswith("error:")
        assert data["status"] == "degraded"
    finally:
        redis_mod.get_settings = original_settings
        redis_mod._redis_client = None


def test_readiness_probe_skips_redis_when_not_configured() -> None:
    """Readiness probe should not include Redis check when not configured."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "redis" not in data["checks"]
    assert data["checks"]["database"] == "ok"
