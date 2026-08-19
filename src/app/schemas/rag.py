"""RAG API schemas for search and question answering."""

from typing import Any

from pydantic import BaseModel, Field


class RAGSearchRequest(BaseModel):
    """Request to search document chunks."""

    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")
    threshold: float = Field(
        0.7, ge=0.0, le=1.0, description="Similarity threshold for vector search"
    )


class RAGSearchResult(BaseModel):
    """A single search result."""

    chunk_id: str
    document_id: str
    content: str
    score: float | None = None
    document_title: str | None = None
    chunk_index: int | None = None


class RAGSearchResponse(BaseModel):
    """Response from a RAG search."""

    query: str
    results: list[RAGSearchResult]
    total: int


class RAGAskRequest(BaseModel):
    """Request to ask a question using RAG."""

    question: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")
    threshold: float = Field(
        0.7, ge=0.0, le=1.0, description="Similarity threshold for vector search"
    )


class RAGAskResponse(BaseModel):
    """Response from a RAG question."""

    answer: str
    sources: list[dict[str, Any]]
    provider: str
    model: str
    token_count: int | None = None
