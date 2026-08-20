"""Tests for document upload, management, and ownership isolation."""

from fastapi.testclient import TestClient

from app.main import create_app


def _register_and_login(
    client: TestClient, email: str, password: str = "TestPassword123!"
) -> str:
    """Helper to register a user and return their access token."""
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


def test_document_upload_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert response.status_code in (401, 422)


def test_document_list_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/documents/")
    assert response.status_code in (401, 422)


def test_document_get_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")
    assert response.status_code in (401, 422)


def test_document_delete_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.delete("/api/v1/documents/00000000-0000-0000-0000-000000000000")
    assert response.status_code in (401, 422)


# --- Upload ---


def test_text_document_upload_persists_content() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "upload-doc@example.com")

    response = client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "notes.txt",
                b"Alpha beta gamma\nDelta epsilon.",
                "text/plain",
            )
        },
        headers=_auth(token),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "notes.txt"
    assert payload["status"] == "processed"
    assert payload["document_metadata"]["content_length"] == 31
    assert payload["content_excerpt"]


def test_document_content_stored_after_upload() -> None:
    """Verify Document.content is populated with extracted text."""
    client = TestClient(create_app())
    token = _register_and_login(client, "content-store@example.com")
    headers = _auth(token)

    content = "The quick brown fox jumps over the lazy dog."
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("content.txt", content.encode(), "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    # Fetch document and verify content column is populated
    resp = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert resp.status_code == 200
    # DocumentResponse doesn't include content directly, but we can
    # verify the content_excerpt is derived from the stored content
    assert resp.json()["content_excerpt"]


def test_upload_rejects_unsupported_file() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "unsupported@example.com")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.exe", b"not-a-real-doc", "application/octet-stream")},
        headers=_auth(token),
    )
    assert response.status_code == 415


def test_upload_rejects_empty_file() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "empty-upload@example.com")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
        headers=_auth(token),
    )
    assert response.status_code == 400


def test_upload_rejects_empty_text_content() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "whitespace@example.com")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("whitespace.txt", b"   \n\n  \t  ", "text/plain")},
        headers=_auth(token),
    )
    assert response.status_code == 422


# --- List / Get ---


def test_list_documents() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "list-doc@example.com")
    headers = _auth(token)

    client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc1.txt", b"First document content", "text/plain")},
        headers=headers,
    )
    client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc2.txt", b"Second document content", "text/plain")},
        headers=headers,
    )

    resp = client.get("/api/v1/documents/", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["documents"]) == 2
    # Newest first
    assert data["documents"][0]["title"] == "doc2.txt"
    assert "chunk_count" in data["documents"][0]


def test_get_document_by_id() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "get-doc@example.com")
    headers = _auth(token)

    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("mydoc.txt", b"Content here", "text/plain")},
        headers=headers,
    )
    doc_id = resp.json()["id"]

    resp = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == doc_id
    assert resp.json()["title"] == "mydoc.txt"


def test_get_nonexistent_document_returns_404() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "404-doc@example.com")

    resp = client.get(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000",
        headers=_auth(token),
    )
    assert resp.status_code == 404


def test_empty_list_returns_zero_total() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "empty-list@example.com")

    resp = client.get("/api/v1/documents/", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["documents"] == []


# --- Delete ---


def test_delete_document() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "delete-doc@example.com")
    headers = _auth(token)

    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("to-delete.txt", b"Delete me", "text/plain")},
        headers=headers,
    )
    doc_id = resp.json()["id"]

    del_resp = client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert get_resp.status_code == 404


def test_delete_nonexistent_document_returns_404() -> None:
    client = TestClient(create_app())
    token = _register_and_login(client, "del-404@example.com")

    resp = client.delete(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000",
        headers=_auth(token),
    )
    assert resp.status_code == 404


# --- Cross-user isolation ---


def test_documents_are_isolated_between_users() -> None:
    """User A cannot see or access User B's documents."""
    client = TestClient(create_app())

    token_a = _register_and_login(client, "user-a@example.com")
    token_b = _register_and_login(client, "user-b@example.com")

    # User A uploads a document
    resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("secret.txt", b"User A secret content", "text/plain")},
        headers=_auth(token_a),
    )
    doc_a_id = resp.json()["id"]

    # User B lists — should be empty
    list_b = client.get("/api/v1/documents/", headers=_auth(token_b))
    assert list_b.json()["total"] == 0

    # User B cannot get User A's document
    get_b = client.get(f"/api/v1/documents/{doc_a_id}", headers=_auth(token_b))
    assert get_b.status_code == 404

    # User B cannot delete User A's document
    del_b = client.delete(f"/api/v1/documents/{doc_a_id}", headers=_auth(token_b))
    assert del_b.status_code == 404

    # User A can still see their document
    get_a = client.get(f"/api/v1/documents/{doc_a_id}", headers=_auth(token_a))
    assert get_a.status_code == 200
