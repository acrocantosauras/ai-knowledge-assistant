"""Tests for health check endpoints."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check_returns_ok() -> None:
    """Liveness probe returns 200 with basic info."""
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "AI Knowledge Assistant"
    assert data["environment"] in ("development", "test")


def test_readiness_check_returns_ok() -> None:
    """Readiness probe returns 200 when database is reachable."""
    client = TestClient(create_app())

    response = client.get("/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "AI Knowledge Assistant"
    assert data["checks"]["database"] == "ok"
    assert data["environment"] in ("development", "test")
