"""Tests for user preferences API endpoints."""

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


# --- Authentication ---


def test_get_preferences_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/users/me/preferences")
    assert response.status_code in (401, 422)


def test_update_preferences_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.patch(
        "/api/v1/users/me/preferences",
        json={"theme": "dark"},
    )
    assert response.status_code in (401, 422)


# --- Get preferences ---


def test_get_preferences_returns_defaults() -> None:
    """New user should get empty/default preferences."""
    client = TestClient(create_app())
    token = _register_and_login(client, "prefs-default@example.com")

    response = client.get(
        "/api/v1/users/me/preferences",
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


# --- Update preferences ---


def test_update_theme_preference() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "prefs-theme@example.com")

    response = client.patch(
        "/api/v1/users/me/preferences",
        json={"theme": "dark"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["theme"] == "dark"


def test_update_llm_preferences() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "prefs-llm@example.com")

    response = client.patch(
        "/api/v1/users/me/preferences",
        json={
            "default_model": "gpt-4o",
            "default_temperature": 0.5,
            "default_max_tokens": 2048,
        },
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["default_model"] == "gpt-4o"
    assert data["default_temperature"] == 0.5
    assert data["default_max_tokens"] == 2048


def test_update_rag_preferences() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "prefs-rag@example.com")

    response = client.patch(
        "/api/v1/users/me/preferences",
        json={
            "default_rag_limit": 10,
            "default_rag_threshold": 0.8,
        },
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["default_rag_limit"] == 10
    assert data["default_rag_threshold"] == 0.8


def test_preferences_persist_after_update() -> None:
    """Preferences should be persisted and retrievable."""
    client = TestClient(create_app())
    token = _register_and_login(client, "prefs-persist@example.com")

    # Update
    client.patch(
        "/api/v1/users/me/preferences",
        json={"theme": "light", "language": "es"},
        headers=_auth(token),
    )

    # Retrieve
    response = client.get(
        "/api/v1/users/me/preferences",
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["theme"] == "light"
    assert data["language"] == "es"


def test_partial_preference_update_merges() -> None:
    """Partial updates should merge with existing preferences."""
    client = TestClient(create_app())
    token = _register_and_login(client, "prefs-merge@example.com")

    # Set initial preferences
    client.patch(
        "/api/v1/users/me/preferences",
        json={"theme": "dark", "language": "en"},
        headers=_auth(token),
    )

    # Update only theme
    response = client.patch(
        "/api/v1/users/me/preferences",
        json={"theme": "light"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["theme"] == "light"
    assert data["language"] == "en"  # Preserved


# --- Profile ---


def test_get_user_profile() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "profile-test@example.com")

    response = client.get(
        "/api/v1/users/me/profile",
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "profile-test@example.com"
    assert data["is_active"] is True
    assert "preferences" in data


def test_profile_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/users/me/profile")
    assert response.status_code in (401, 422)


def test_preferences_validation_rejects_bad_temperature() -> None:
    """Temperature must be between 0.0 and 2.0."""
    client = TestClient(create_app())
    token = _register_and_login(client, "prefs-validation@example.com")

    response = client.patch(
        "/api/v1/users/me/preferences",
        json={"default_temperature": 5.0},
        headers=_auth(token),
    )
    assert response.status_code == 422
