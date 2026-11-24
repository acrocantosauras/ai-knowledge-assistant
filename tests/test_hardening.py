"""Regression tests for production hardening and upload robustness."""

import io

import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.services import documents as documents_service

GOOD_SECRET = "x" * 48
GOOD_DB = "postgresql+asyncpg://u:Str0ngPw@postgres:5432/db"


def _prod(**overrides) -> Settings:
    values = {
        "environment": "production",
        "jwt_secret_key": GOOD_SECRET,
        "database_url": GOOD_DB,
        "metrics_token": "m" * 20,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_accepts_valid_config() -> None:
    assert _prod().environment == "production"


@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_secret_key": ""},
        {"jwt_secret_key": "change-me-to-a-random-secret-key"},
        {"jwt_secret_key": "short"},
        {"cors_origins": ["*"]},
        {"database_url": "postgresql+asyncpg://u:ai_knowledge_password@h/db"},
    ],
)
def test_production_rejects_insecure_config(overrides) -> None:
    with pytest.raises(ValidationError):
        _prod(**overrides)


def _headers(client: TestClient) -> dict[str, str]:
    creds = {"email": "hard@example.com", "password": "TestPassword123!"}
    client.post("/api/v1/auth/register", json={**creds, "display_name": "h"})
    token = client.post("/api/v1/auth/login", json=creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_docx_upload_extracts_text(client: TestClient) -> None:
    doc = DocxDocument()
    doc.add_paragraph("Paris is the capital of France.")
    buf = io.BytesIO()
    doc.save(buf)
    resp = client.post(
        "/api/v1/documents/upload",
        headers=_headers(client),
        files={"file": ("a.docx", buf.getvalue(), "application/octet-stream")},
    )
    assert resp.status_code == 201, resp.text


def test_corrupt_pdf_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/documents/upload",
        headers=_headers(client),
        files={"file": ("bad.pdf", b"not a pdf", "application/pdf")},
    )
    assert resp.status_code == 422


def test_non_utf8_txt_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/documents/upload",
        headers=_headers(client),
        files={"file": ("bad.txt", b"\xff\xfe\x00\x80", "text/plain")},
    )
    assert resp.status_code == 422


def test_oversize_upload_returns_413(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(documents_service, "MAX_FILE_SIZE_BYTES", 10)
    resp = client.post(
        "/api/v1/documents/upload",
        headers=_headers(client),
        files={"file": ("big.txt", b"a" * 100, "text/plain")},
    )
    assert resp.status_code == 413


def test_unknown_api_path_is_not_swallowed_by_spa(client: TestClient) -> None:
    assert client.get("/api/v1/nope").status_code == 404
