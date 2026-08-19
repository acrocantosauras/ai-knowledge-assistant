"""Conversation API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.core.metrics import CONVERSATIONS_CREATED_TOTAL
from app.db.models.user import User
from app.schemas.conversations import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    ConversationWithMessages,
    MessageCreate,
    MessageResponse,
)
from app.services import conversations as conversation_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post(
    "/",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    data: ConversationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConversationResponse:
    """Create a new conversation."""
    conversation = await conversation_service.create_conversation(
        session=db,
        user_id=current_user.id,
        title=data.title,
        metadata=data.metadata,
    )
    await db.commit()
    CONVERSATIONS_CREATED_TOTAL.labels(user_id=str(current_user.id)).inc()
    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        status=conversation.status,
        metadata=conversation.conversation_metadata,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=0,
    )


@router.get("/", response_model=ConversationListResponse)
async def list_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ConversationListResponse:
    """List conversations for the current user."""
    conversations = await conversation_service.list_conversations(
        session=db,
        user_id=current_user.id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    conversation_responses = []
    for conv in conversations:
        messages = await conversation_service.get_conversation_messages(
            session=db,
            conversation_id=conv.id,
            user_id=current_user.id,
        )
        conversation_responses.append(
            ConversationResponse(
                id=conv.id,
                user_id=conv.user_id,
                title=conv.title,
                status=conv.status,
                metadata=conv.conversation_metadata,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=len(messages),
            )
        )

    return ConversationListResponse(
        conversations=conversation_responses,
        total=len(conversations),
        limit=limit,
        offset=offset,
    )


@router.get("/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConversationWithMessages:
    """Get a conversation with its messages."""
    conversation = await conversation_service.get_conversation(
        session=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        include_messages=True,
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages = [
        MessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            user_id=msg.user_id,
            role=msg.role,
            content=msg.content,
            token_count=msg.token_count,
            metadata=msg.message_metadata,
            created_at=msg.created_at,
            updated_at=msg.updated_at,
        )
        for msg in conversation.messages
    ]

    return ConversationWithMessages(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        status=conversation.status,
        metadata=conversation.conversation_metadata,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(messages),
        messages=messages,
    )


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    data: ConversationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConversationResponse:
    """Update a conversation."""
    conversation = await conversation_service.update_conversation(
        session=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        title=data.title,
        status=data.status,
        metadata=data.metadata,
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    await db.commit()

    messages = await conversation_service.get_conversation_messages(
        session=db,
        conversation_id=conversation.id,
        user_id=current_user.id,
    )

    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        status=conversation.status,
        metadata=conversation.conversation_metadata,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(messages),
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """Delete a conversation."""
    deleted = await conversation_service.delete_conversation(
        session=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    await db.commit()


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_message_to_conversation(
    conversation_id: UUID,
    data: MessageCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """Add a message to a conversation."""
    message = await conversation_service.add_message(
        session=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        role=data.role,
        content=data.content,
        token_count=data.token_count,
        metadata=data.metadata,
    )

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    await db.commit()

    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        user_id=message.user_id,
        role=message.role,
        content=message.content,
        token_count=message.token_count,
        metadata=message.message_metadata,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )

