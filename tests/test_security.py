"""Security-focused tests."""

from fastapi.testclient import TestClient

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
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
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
