"""QA schemas for question answering API."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    """Request to ask a question."""

    question: str = Field(..., min_length=1, max_length=2000)
    conversation_id: UUID | None = Field(
        None,
        description="Optional conversation ID to continue existing conversation",
    )
    limit: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")
    threshold: float = Field(
        0.7, ge=0.0, le=1.0, description="Similarity threshold for vector search"
    )


class QuestionResponse(BaseModel):
    """Response from a question."""

    answer: str
    sources: list[dict[str, Any]]
    provider: str
    model: str
    token_count: int | None = None
    conversation_id: UUID
    question_message_id: UUID
    answer_message_id: UUID


class StreamingResponse(BaseModel):
    """Response chunk for streaming."""

    type: str  # "answer" | "sources" | "error"
    content: str | None = None
    is_final: bool = False
    sources: list[dict[str, Any]] | None = None
    provider: str | None = None
    model: str | None = None
    error: str | None = None
