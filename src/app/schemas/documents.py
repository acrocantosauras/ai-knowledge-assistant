from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    source_type: str
    source_uri: str | None = None
    content_type: str | None = None
    status: str
    checksum: str | None = None
    document_metadata: dict[str, Any] = Field(default_factory=dict)
    content_excerpt: str = ""
    created_at: datetime
    updated_at: datetime


class DocumentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    user_id: UUID
    chunk_index: int
    content: str
    token_count: int | None = None
    chunk_metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    source_type: str
    source_uri: str | None = None
    content_type: str | None = None
    status: str
    checksum: str | None = None
    document_metadata: dict[str, Any] = Field(default_factory=dict)
    content_excerpt: str = ""
    created_at: datetime
    updated_at: datetime
    chunk_count: int
