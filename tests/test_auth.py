import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_register_user(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "integration-test@example.com",
            "password": "TestPassword123!",
            "display_name": "Integration Test",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["email"] == "integration-test@example.com"
    assert data["display_name"] == "Integration Test"
    assert data["is_active"] is True
    assert "password_hash" not in data


def test_duplicate_registration(client: TestClient) -> None:
    payload = {
        "email": "duplicate-test@example.com",
        "password": "TestPassword123!",
        "display_name": "Duplicate Test",
    }

    first_response = client.post(
        "/api/v1/auth/register",
        json=payload,
    )
    second_response = client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_login_returns_access_token(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "login-test@example.com",
            "password": "TestPassword123!",
            "display_name": "Login Test",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "login-test@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert data["access_token"]


def test_login_rejects_wrong_password(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrong-password@example.com",
            "password": "TestPassword123!",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrong-password@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_rejects_unknown_user(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "unknown-user@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."
