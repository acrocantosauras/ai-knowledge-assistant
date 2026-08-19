"""Security-focused tests."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import create_app

# --- Password hashing ---


def test_password_hash_can_be_verified() -> None:
    password = "TestPassword123!"
    hashed_password = hash_password(password)
    assert hashed_password != password
    assert verify_password(password, hashed_password) is True
    assert verify_password("WrongPassword!", hashed_password) is False


def test_different_hashes_for_same_password() -> None:
    """Argon2 produces different salts each time."""
    h1 = hash_password("SamePassword123!")
    h2 = hash_password("SamePassword123!")
    assert h1 != h2
    assert verify_password("SamePassword123!", h1)
    assert verify_password("SamePassword123!", h2)


# --- JWT tokens ---


def test_access_token_can_be_created_and_decoded() -> None:
    subject = "00000000-0000-0000-0000-000000000001"
    token = create_access_token(subject)
    assert decode_access_token(token) == subject


def test_invalid_access_token_is_rejected() -> None:
    assert decode_access_token("not-a-real-token") is None


def test_empty_token_is_rejected() -> None:
    assert decode_access_token("") is None


def test_tampered_token_is_rejected() -> None:
    token = create_access_token("user-id-123")
    # Modify a character in the MIDDLE of the signature where all 6 base64url
    # bits are meaningful.  Changing index 10 guarantees the decoded bytes
    # differ and the HMAC verification fails.
    chars = list(token)
    original = chars[10]
    chars[10] = "A" if original != "A" else "B"
    tampered = "".join(chars)
    assert decode_access_token(tampered) is None


# --- Authentication endpoints ---


def test_login_rejects_wrong_password() -> None:
    client = TestClient(create_app())
    client.post(
        "/api/v1/auth/register",
        json={"email": "sec-wrong@example.com", "password": "TestPassword123!"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "sec-wrong@example.com", "password": "WrongPassword123!"},
    )
    assert resp.status_code == 401


def test_login_rejects_unknown_email() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "TestPassword123!"},
    )
    assert resp.status_code == 401


def test_duplicate_registration_rejected() -> None:
    client = TestClient(create_app())
    payload = {"email": "dup@example.com", "password": "TestPassword123!"}
    r1 = client.post("/api/v1/auth/register", json=payload)
    r2 = client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 409


def test_password_not_in_response() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "no-hash@example.com", "password": "TestPassword123!"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "password" not in data
    assert "password_hash" not in data


# --- Protected endpoints without token ---


def test_protected_endpoints_reject_missing_token() -> None:
    client = TestClient(create_app())
    endpoints = [
        ("GET", "/api/v1/documents/"),
        ("GET", "/api/v1/conversations/"),
        ("POST", "/api/v1/conversations/"),
        ("POST", "/api/v1/rag/search"),
        ("POST", "/api/v1/rag/ask"),
        ("POST", "/api/v1/qa/ask"),
    ]
    for method, url in endpoints:
        if method == "GET":
            resp = client.get(url)
        else:
            resp = client.post(url, json={})
        assert resp.status_code in (401, 422), (
            f"{method} {url} returned {resp.status_code}"
        )


def test_protected_endpoints_reject_invalid_token() -> None:
    client = TestClient(create_app())
    bad_headers = {"Authorization": "Bearer invalid-token-xyz"}
    endpoints = [
        ("GET", "/api/v1/documents/"),
        ("GET", "/api/v1/conversations/"),
        ("POST", "/api/v1/rag/search"),
    ]
    for method, url in endpoints:
        if method == "GET":
            resp = client.get(url, headers=bad_headers)
        else:
            resp = client.post(url, json={"query": "test"}, headers=bad_headers)
        assert resp.status_code == 401, f"{method} {url} returned {resp.status_code}"


def test_malformed_auth_header_rejected() -> None:
    client = TestClient(create_app())
    token = create_access_token("user-id")
    resp = client.get(
        "/api/v1/documents/",
        headers={"Authorization": token},
    )
    assert resp.status_code in (401, 422)


# --- Expired tokens ---


def test_expired_token_is_rejected() -> None:
    """Expired tokens must be rejected."""
    settings = get_settings()
    payload = {
        "sub": "user-id-123",
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(token) is None


def test_expired_token_rejected_by_endpoint() -> None:
    """Protected endpoint rejects expired tokens with 401."""
    settings = get_settings()
    payload = {
        "sub": "00000000-0000-0000-0000-000000000001",
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    client = TestClient(create_app())
    resp = client.get(
        "/api/v1/documents/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


# --- Algorithm confusion attacks ---


def test_token_signed_with_wrong_algorithm_rejected() -> None:
    """Token signed with a different algorithm than configured is rejected."""
    # Sign with 'none' algorithm — should not validate with configured algorithm
    payload = {
        "sub": "user-id-123",
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    malicious_token = jwt.encode(
        payload,
        "",
        algorithm="none",
    )
    assert decode_access_token(malicious_token) is None


def test_algorithm_confusion_with_different_secret_rejected() -> None:
    """Token signed with correct algorithm but wrong secret is rejected."""
    settings = get_settings()
    payload = {
        "sub": "user-id-123",
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = jwt.encode(
        payload,
        "wrong-secret-key",
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(token) is None


# --- Missing subject claim ---


def test_token_without_sub_claim_rejected() -> None:
    """Token without a 'sub' claim is rejected."""
    settings = get_settings()
    payload = {
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(token) is None


def test_token_with_empty_sub_claim_rejected() -> None:
    """Token with an empty 'sub' claim is rejected."""
    settings = get_settings()
    payload = {
        "sub": "",
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(token) is None


def test_token_with_non_string_sub_claim_rejected() -> None:
    """Token with a non-string 'sub' claim is rejected."""
    settings = get_settings()
    payload = {
        "sub": 12345,
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(token) is None


# --- Nonexistent user ---


def test_nonexistent_user_rejected_by_endpoint() -> None:
    """Token referencing a nonexistent user is rejected with 401."""
    fake_user_id = "00000000-0000-0000-0000-999999999999"
    token = create_access_token(fake_user_id)
    client = TestClient(create_app())
    resp = client.get(
        "/api/v1/documents/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


# --- User isolation (User A cannot access User B's resources) ---


def test_user_a_cannot_access_user_b_documents() -> None:
    """User A's token cannot access User B's documents."""
    client = TestClient(create_app())

    # Register User A
    client.post(
        "/api/v1/auth/register",
        json={"email": "user-a-iso@example.com", "password": "TestPassword123!"},
    )
    login_a = client.post(
        "/api/v1/auth/login",
        json={"email": "user-a-iso@example.com", "password": "TestPassword123!"},
    )
    token_a = login_a.json()["access_token"]

    # Register User B
    client.post(
        "/api/v1/auth/register",
        json={"email": "user-b-iso@example.com", "password": "TestPassword123!"},
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": "user-b-iso@example.com", "password": "TestPassword123!"},
    )
    token_b = login_b.json()["access_token"]

    # User B creates a conversation
    resp_b = client.post(
        "/api/v1/conversations/",
        json={"title": "User B private"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 201
    conv_id = resp_b.json()["id"]

    # User A tries to access User B's conversation — should get 404
    resp_a = client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a.status_code == 404

    # User A lists conversations — should be empty
    resp_a_list = client.get(
        "/api/v1/conversations/",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a_list.status_code == 200
    assert resp_a_list.json()["total"] == 0


def test_user_a_cannot_access_user_b_preferences() -> None:
    """User A's token cannot modify User B's preferences."""
    client = TestClient(create_app())

    # Register User A and B
    client.post(
        "/api/v1/auth/register",
        json={"email": "pref-a@example.com", "password": "TestPassword123!"},
    )
    client.post(
        "/api/v1/auth/register",
        json={"email": "pref-b@example.com", "password": "TestPassword123!"},
    )

    login_a = client.post(
        "/api/v1/auth/login",
        json={"email": "pref-a@example.com", "password": "TestPassword123!"},
    )
    token_a = login_a.json()["access_token"]

    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": "pref-b@example.com", "password": "TestPassword123!"},
    )
    token_b = login_b.json()["access_token"]

    # User B updates preferences
    client.patch(
        "/api/v1/users/me/preferences",
        json={"theme": "dark"},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # User A reads their own preferences — should be default (not dark)
    resp_a = client.get(
        "/api/v1/users/me/preferences",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a.status_code == 200
    assert resp_a.json().get("theme") != "dark"


def test_user_a_cannot_access_user_b_profile() -> None:
    """User A's token only shows User A's profile, never User B's."""
    client = TestClient(create_app())

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "prof-a@example.com",
            "password": "TestPassword123!",
            "display_name": "User A",
        },
    )
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "prof-b@example.com",
            "password": "TestPassword123!",
            "display_name": "User B",
        },
    )

    login_a = client.post(
        "/api/v1/auth/login",
        json={"email": "prof-a@example.com", "password": "TestPassword123!"},
    )
    token_a = login_a.json()["access_token"]

    # User A gets profile — must be User A, not User B
    resp = client.get(
        "/api/v1/users/me/profile",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "prof-a@example.com"
    assert data["display_name"] == "User A"


# --- Production configuration ---


def test_production_rejects_missing_jwt_secret() -> None:
    """Production environment requires APP_JWT_SECRET_KEY to be set."""
    with pytest.raises(ValidationError, match="APP_JWT_SECRET_KEY is required"):
        Settings(environment="production", jwt_secret_key="")


def test_production_rejects_placeholder_jwt_secret() -> None:
    """Production environment rejects the default placeholder secret."""
    with pytest.raises(ValidationError, match="must not be the default"):
        Settings(
            environment="production",
            jwt_secret_key="change-me-to-a-random-secret-key",
        )


def test_development_allows_empty_jwt_secret() -> None:
    """Development environment allows empty JWT secret (convenience for local dev)."""
    settings = Settings(environment="development", jwt_secret_key="")
    assert settings.jwt_secret_key == ""
