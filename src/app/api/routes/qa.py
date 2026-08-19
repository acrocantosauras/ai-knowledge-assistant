"""QA API endpoints for question answering."""

import time
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.config import get_settings
from app.core.metrics import QA_LATENCY_SECONDS, QA_QUESTIONS_TOTAL
from app.core.rate_limit import limiter
from app.db.models.user import User
from app.schemas.qa import QuestionRequest, QuestionResponse
from app.schemas.qa import StreamingResponse as StreamingResponseSchema
from app.services import conversations as conversation_service
from app.services.qa import ask_question, ask_question_stream

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/ask", response_model=QuestionResponse, status_code=status.HTTP_200_OK)
@limiter.limit(get_settings().rate_limit_qa)
async def ask_question_endpoint(
    request: Request,
    data: QuestionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> QuestionResponse:
    """Ask a question and get an answer using RAG.
    
    If conversation_id is provided, the Q&A will be saved to that conversation.
    If not provided, a new conversation will be created.
    """
    start_time = time.monotonic()
    conversation_id = data.conversation_id
    
    # If no conversation provided, create one with LLM-generated title
    if conversation_id is None:
        conversation = await conversation_service.create_conversation(
            session=db,
            user_id=current_user.id,
            first_message=data.question,
        )
        await db.flush()
        conversation_id = conversation.id
    else:
        # Verify conversation exists and belongs to user
        conversation = await conversation_service.get_conversation(
            session=db,
            conversation_id=conversation_id,
            user_id=current_user.id,
        )
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
    
    # Ask the question using QA service
    qa_response = await ask_question(
        session=db,
        user_id=current_user.id,
        question=data.question,
        limit=data.limit,
        threshold=data.threshold,
    )
    
    # Save user message (question)
    question_message = await conversation_service.add_message(
        session=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        role="user",
        content=data.question,
        metadata={"type": "question"},
    )
    
    if not question_message:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save question message",
        )
    
    # Save assistant message (answer)
    answer_message = await conversation_service.add_message(
        session=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        role="assistant",
        content=qa_response.answer,
        token_count=qa_response.token_count,
        metadata={
            "type": "answer",
            "sources": qa_response.sources,
            "provider": qa_response.provider,
            "model": qa_response.model,
        },
    )
    
    if not answer_message:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save answer message",
        )
    
    await db.commit()

    # Record metrics
    elapsed = time.monotonic() - start_time
    QA_QUESTIONS_TOTAL.labels(provider=qa_response.provider).inc()
    QA_LATENCY_SECONDS.labels(provider=qa_response.provider).observe(elapsed)

    return QuestionResponse(
        answer=qa_response.answer,
        sources=qa_response.sources,
        provider=qa_response.provider,
        model=qa_response.model,
        token_count=qa_response.token_count,
        conversation_id=conversation_id,
        question_message_id=question_message.id,
        answer_message_id=answer_message.id,
    )


@router.post("/ask/stream")
@limiter.limit(get_settings().rate_limit_qa)
async def ask_question_stream_endpoint(
    request: Request,
    data: QuestionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> StreamingResponse:
    """Ask a question and stream the answer using RAG with Server-Sent Events (SSE).
    
    If conversation_id is provided, the Q&A will be saved to that conversation.
    If not provided, a new conversation will be created.
    
    Returns a stream of JSON objects with the following types:
    - sources: Contains source documents
    - answer: Contains answer chunks with is_final flag
    - error: Contains error message
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        conversation_id = data.conversation_id
        question_message = None
        answer_message = None
        full_answer = ""
        stream_start_time = time.monotonic()
        
        try:
            # If no conversation provided, create one with LLM-generated title
            if conversation_id is None:
                conversation = await conversation_service.create_conversation(
                    session=db,
                    user_id=current_user.id,
                    first_message=data.question,
                )
                await db.flush()
                conversation_id = conversation.id
            else:
                # Verify conversation exists and belongs to user
                conversation = await conversation_service.get_conversation(
                    session=db,
                    conversation_id=conversation_id,
                    user_id=current_user.id,
                )
                if not conversation:
                    error_data = StreamingResponseSchema(
                        type="error", error="Conversation not found"
                    )
                    yield f"data: {error_data.model_dump_json()}\n\n"
                    return
            
            # Save user message (question) immediately
            question_message = await conversation_service.add_message(
                session=db,
                conversation_id=conversation_id,
                user_id=current_user.id,
                role="user",
                content=data.question,
                metadata={"type": "question"},
            )
            
            if not question_message:
                error_data = StreamingResponseSchema(
                    type="error", error="Failed to save question message"
                )
                yield f"data: {error_data.model_dump_json()}\n\n"
                return
            
            # Stream the answer
            async for chunk in ask_question_stream(
                session=db,
                user_id=current_user.id,
                question=data.question,
                limit=data.limit,
                threshold=data.threshold,
            ):
                # Yield the chunk as SSE
                chunk_data = StreamingResponseSchema(**chunk)
                yield f"data: {chunk_data.model_dump_json()}\n\n"
                
                # Accumulate answer content
                if chunk.get("type") == "answer":
                    content = chunk.get("content", "")
                    if content:
                        full_answer += content
                    
                    # Save answer message when complete
                    if chunk.get("is_final"):
                        answer_message = await conversation_service.add_message(
                            session=db,
                            conversation_id=conversation_id,
                            user_id=current_user.id,
                            role="assistant",
                            content=full_answer,
                            token_count=None,  # Will be updated after
                            metadata={
                                "type": "answer",
                                "sources": chunk.get("sources", []),
                                "provider": chunk.get("provider", "unknown"),
                                "model": chunk.get("model", "unknown"),
                            },
                        )
                        
                        if answer_message:
                            await db.commit()

                        # Record metrics for streaming endpoint
                        provider = chunk.get("provider", "unknown")
                        QA_QUESTIONS_TOTAL.labels(provider=provider).inc()
                        QA_LATENCY_SECONDS.labels(provider=provider).observe(
                            time.monotonic() - stream_start_time
                        )
            
        except Exception as e:
            error_data = StreamingResponseSchema(type="error", error=str(e))
            yield f"data: {error_data.model_dump_json()}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
