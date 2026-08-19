"""QA service for question answering with RAG integration."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm import get_llm_service
from app.services.rag import search_document_chunks_with_embeddings

# System prompt for QA
QA_SYSTEM_PROMPT = """You are an AI Knowledge Assistant.
Answer questions based on the provided documents.
Your responses should be:
- Accurate and based only on the provided context
- Concise but complete
- Clear about what information comes from which document
- Honest when the context doesn't contain enough information

If the context doesn't contain relevant information, say so clearly.
Cite your sources by referencing document numbers (e.g., [Document 1])."""


@dataclass(slots=True)
class QAResponse:
    """Response from the QA system."""

    answer: str
    sources: list[dict[str, Any]]
    provider: str
    model: str
    token_count: int | None = None
    conversation_id: UUID | None = None
    message_id: UUID | None = None


async def ask_question(
    session: AsyncSession,
    user_id: UUID,
    question: str,
    limit: int = 5,
    threshold: float = 0.7,
) -> QAResponse:
    """Ask a question and get an answer using RAG.

    Args:
        session: Database session
        user_id: ID of the user asking the question
        question: The question to ask
        limit: Maximum number of document chunks to retrieve
        threshold: Similarity threshold for vector search

    Returns:
        QAResponse with answer and source references
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty")

    # Retrieve relevant chunks using embeddings
    chunks = await search_document_chunks_with_embeddings(
        session=session,
        user_id=user_id,
        query=question,
        limit=limit,
        threshold=threshold,
    )

    if not chunks:
        return QAResponse(
            answer=(
                "I couldn't find any relevant documents to answer your "
                "question. Please upload relevant documents first, or try "
                "rephrasing your question."
            ),
            sources=[],
            provider="mock",
            model="mock",
        )

    # Build context from chunks
    context_texts = []
    sources = []
    for _i, chunk in enumerate(chunks):
        context_texts.append(chunk.content)
        sources.append({
            "document_id": str(chunk.document_id),
            "chunk_id": str(chunk.id),
            "content_preview": (
                chunk.content[:200] + "..."
                if len(chunk.content) > 200
                else chunk.content
            ),
            "score": (
                float(chunk.score) if getattr(chunk, "score", None) is not None
                else None
            ),
        })

    # Truncate context if too long
    max_context_chars = 32000
    total_chars = sum(len(c) for c in context_texts)
    if total_chars > max_context_chars:
        context_texts = _truncate_context(context_texts, max_context_chars)

    # Get LLM service and generate answer
    llm_service = get_llm_service()
    response = await llm_service.generate_with_context(
        system_prompt=QA_SYSTEM_PROMPT,
        user_message=question,
        context=context_texts,
    )

    return QAResponse(
        answer=response.content,
        sources=sources,
        provider=response.provider,
        model=response.model,
        token_count=response.token_count,
    )


async def ask_question_stream(
    session: AsyncSession,
    user_id: UUID,
    question: str,
    limit: int = 5,
    threshold: float = 0.7,
) -> AsyncGenerator[dict[str, Any], None]:
    """Ask a question and stream the answer using RAG.

    Args:
        session: Database session
        user_id: ID of the user asking the question
        question: The question to ask
        limit: Maximum number of document chunks to retrieve
        threshold: Similarity threshold for vector search

    Yields:
        Dictionary chunks with answer tokens and metadata
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty")

    # Retrieve relevant chunks using embeddings
    chunks = await search_document_chunks_with_embeddings(
        session=session,
        user_id=user_id,
        query=question,
        limit=limit,
        threshold=threshold,
    )

    if not chunks:
        yield {
            "type": "answer",
            "content": (
                "I couldn't find any relevant documents to answer your "
                "question. Please upload relevant documents first, or try "
                "rephrasing your question."
            ),
            "is_final": True,
            "sources": [],
            "provider": "mock",
            "model": "mock",
        }
        return

    # Build context from chunks
    context_texts = []
    sources = []
    for _i, chunk in enumerate(chunks):
        context_texts.append(chunk.content)
        sources.append({
            "document_id": str(chunk.document_id),
            "chunk_id": str(chunk.id),
            "content_preview": (
                chunk.content[:200] + "..."
                if len(chunk.content) > 200
                else chunk.content
            ),
            "score": (
                float(chunk.score) if getattr(chunk, "score", None) is not None
                else None
            ),
        })

    # Truncate context if too long
    max_context_chars = 32000
    total_chars = sum(len(c) for c in context_texts)
    if total_chars > max_context_chars:
        context_texts = _truncate_context(context_texts, max_context_chars)

    # Yield sources first
    yield {
        "type": "sources",
        "sources": sources,
    }

    # Get LLM service and generate streaming answer
    llm_service = get_llm_service()
    async for chunk in llm_service.generate_with_context_stream(
        system_prompt=QA_SYSTEM_PROMPT,
        user_message=question,
        context=context_texts,
    ):
        yield {
            "type": "answer",
            "content": chunk.content,
            "is_final": chunk.is_final,
            "provider": llm_service.provider_name,
            "model": llm_service.model_name,
        }


def _truncate_context(context_texts: list[str], max_chars: int) -> list[str]:
    """Truncate context texts to fit within max_chars."""
    total_chars = sum(len(c) for c in context_texts)
    if total_chars <= max_chars:
        return context_texts

    ratio = max_chars / total_chars
    truncated = []
    for text in context_texts:
        keep_chars = int(len(text) * ratio)
        if keep_chars < 100:
            keep_chars = min(100, len(text))
        truncated.append(text[:keep_chars] + "...")

    final_chars = sum(len(c) for c in truncated)
    if final_chars > max_chars:
        excess = final_chars - max_chars
        truncated[-1] = truncated[-1][:-excess - 3] + "..."

    return truncated
