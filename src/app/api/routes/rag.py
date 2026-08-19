"""RAG API endpoints for semantic search and question answering."""

import json
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.config import get_settings
from app.core.metrics import RAG_CHUNKS_RETURNED, RAG_SEARCH_TOTAL
from app.core.rate_limit import limiter
from app.db.models.user import User
from app.schemas.rag import (
    RAGAskRequest,
    RAGAskResponse,
    RAGSearchRequest,
    RAGSearchResponse,
)
from app.services.llm import get_llm_service
from app.services.rag import search_document_chunks_with_embeddings

router = APIRouter(prefix="/rag", tags=["rag"])

# System prompt for RAG
RAG_SYSTEM_PROMPT = """You are an AI Knowledge Assistant.
Answer questions based on the provided documents.
Your responses should be:
- Accurate and based only on the provided context
- Concise but complete
- Clear about what information comes from which document
- Honest when the context doesn't contain enough information

If the context doesn't contain relevant information, say so clearly.
Cite your sources by referencing document numbers (e.g., [Document 1])."""


def _build_context_from_chunks(
    chunks: list[Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Build context texts and source metadata from chunks."""
    context_texts = []
    sources = []
    for _i, chunk in enumerate(chunks):
        context_texts.append(chunk.content)
        sources.append({
            "document_id": str(chunk.document_id),
            "chunk_id": str(chunk.id),
            "document_title": chunk.document.title,
            "chunk_index": chunk.chunk_index,
            "content_preview": (
                chunk.content[:200] + "..."
                if len(chunk.content) > 200
                else chunk.content
            ),
            "score": float(chunk.score) if chunk.score is not None else None,
        })
    return context_texts, sources


def _truncate_context(context_texts: list[str], max_chars: int = 32000) -> list[str]:
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


@router.post(
    "/search",
    response_model=RAGSearchResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(get_settings().rate_limit_rag)
async def search_chunks(
    request: Request,
    data: RAGSearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> RAGSearchResponse:
    """Search document chunks using embeddings or fallback."""
    chunks = await search_document_chunks_with_embeddings(
        session=db,
        user_id=current_user.id,
        query=data.query,
        limit=data.limit,
        threshold=data.threshold,
    )

    RAG_SEARCH_TOTAL.inc()
    RAG_CHUNKS_RETURNED.observe(len(chunks))

    results = [
        {
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "content": chunk.content,
            "score": getattr(chunk, "score", None),
            "document_title": chunk.document.title,
            "chunk_index": chunk.chunk_index,
        }
        for chunk in chunks
    ]

    return RAGSearchResponse(query=data.query, results=results, total=len(results))


@router.post(
    "/ask",
    response_model=RAGAskResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(get_settings().rate_limit_qa)
async def ask_question(
    request: Request,
    data: RAGAskRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> RAGAskResponse:
    """Ask a question using RAG pipeline."""
    if not data.question or not data.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty",
        )

    # Retrieve relevant chunks using embeddings
    chunks = await search_document_chunks_with_embeddings(
        session=db,
        user_id=current_user.id,
        query=data.question,
        limit=data.limit,
        threshold=data.threshold,
    )

    if not chunks:
        return RAGAskResponse(
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
    context_texts, sources = _build_context_from_chunks(chunks)

    # Truncate context if too long
    context_texts = _truncate_context(context_texts)

    # Get LLM service and generate answer
    llm_service = get_llm_service()
    response = await llm_service.generate_with_context(
        system_prompt=RAG_SYSTEM_PROMPT,
        user_message=data.question,
        context=context_texts,
    )

    return RAGAskResponse(
        answer=response.content,
        sources=sources,
        provider=response.provider,
        model=response.model,
        token_count=response.token_count,
    )


@router.post(
    "/ask/stream",
    status_code=status.HTTP_200_OK,
)
@limiter.limit(get_settings().rate_limit_qa)
async def ask_question_stream(
    request: Request,
    data: RAGAskRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StreamingResponse:
    """Ask a question using RAG pipeline with streaming response."""

    async def event_generator() -> AsyncGenerator[str, None]:
        if not data.question or not data.question.strip():
            error_data = {
                "type": "error",
                "error": "Question cannot be empty",
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            return

        # Retrieve relevant chunks using embeddings
        chunks = await search_document_chunks_with_embeddings(
            session=db,
            user_id=current_user.id,
            query=data.question,
            limit=data.limit,
            threshold=data.threshold,
        )

        RAG_SEARCH_TOTAL.inc()
        RAG_CHUNKS_RETURNED.observe(len(chunks))

        if not chunks:
            no_answer_data = {
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
            yield f"data: {json.dumps(no_answer_data)}\n\n"
            return

        # Build context from chunks
        context_texts, sources = _build_context_from_chunks(chunks)

        # Truncate context if too long
        context_texts = _truncate_context(context_texts)

        # Yield sources first
        sources_data = {
            "type": "sources",
            "sources": sources,
        }
        yield f"data: {json.dumps(sources_data)}\n\n"

        # Get LLM service and generate streaming answer
        llm_service = get_llm_service()
        async for chunk in llm_service.generate_with_context_stream(
            system_prompt=RAG_SYSTEM_PROMPT,
            user_message=data.question,
            context=context_texts,
        ):
            answer_data = {
                "type": "answer",
                "content": chunk.content,
                "is_final": chunk.is_final,
                "provider": llm_service.provider_name,
                "model": llm_service.model_name,
            }
            yield f"data: {json.dumps(answer_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )