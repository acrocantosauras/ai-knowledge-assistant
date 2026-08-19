"""Conversation management service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.services.llm import get_llm_provider


async def create_conversation(
    session: Session,
    user_id: UUID,
    title: str | None = None,
    metadata: dict | None = None,
    first_message: str | None = None,
) -> Conversation:
    """Create a new conversation.
    
    If title is not provided but first_message is, generate a title from the message.
    """
    if title is None and first_message is not None:
        title = await generate_conversation_title(first_message)
    elif title is None:
        title = "New Conversation"
    
    conversation = Conversation(
        user_id=user_id,
        title=title,
        status="active",
        conversation_metadata=metadata or {},
    )
    session.add(conversation)
    await session.flush()
    await session.refresh(conversation)
    return conversation


async def get_conversation(
    session: Session,
    conversation_id: UUID,
    user_id: UUID,
    include_messages: bool = False,
) -> Conversation | None:
    """Get a conversation by ID."""
    query = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    if include_messages:
        query = query.options(selectinload(Conversation.messages))

    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_conversations(
    session: Session,
    user_id: UUID,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Conversation]:
    """List conversations for a user."""
    query = select(Conversation).where(Conversation.user_id == user_id)

    if status:
        query = query.where(Conversation.status == status)

    query = query.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    return list(result.scalars().all())


async def update_conversation(
    session: Session,
    conversation_id: UUID,
    user_id: UUID,
    title: str | None = None,
    status: str | None = None,
    metadata: dict | None = None,
) -> Conversation | None:
    """Update a conversation."""
    conversation = await get_conversation(session, conversation_id, user_id)
    if not conversation:
        return None

    if title is not None:
        conversation.title = title
    if status is not None:
        conversation.status = status
    if metadata is not None:
        conversation.conversation_metadata = {
            **conversation.conversation_metadata,
            **metadata,
        }

    await session.flush()
    await session.refresh(conversation)
    return conversation


async def delete_conversation(
    session: Session,
    conversation_id: UUID,
    user_id: UUID,
) -> bool:
    """Delete a conversation."""
    conversation = await get_conversation(session, conversation_id, user_id)
    if not conversation:
        return False

    await session.delete(conversation)
    await session.flush()
    return True


async def add_message(
    session: Session,
    conversation_id: UUID,
    user_id: UUID,
    role: str,
    content: str,
    token_count: int | None = None,
    metadata: dict | None = None,
) -> Message | None:
    """Add a message to a conversation."""
    conversation = await get_conversation(session, conversation_id, user_id)
    if not conversation:
        return None

    message = Message(
        conversation_id=conversation_id,
        user_id=user_id,
        role=role,
        content=content,
        token_count=token_count,
        message_metadata=metadata or {},
    )
    session.add(message)
    conversation.updated_at = datetime.now(UTC)

    await session.flush()
    await session.refresh(message)
    return message


async def get_conversation_messages(
    session: Session,
    conversation_id: UUID,
    user_id: UUID,
    limit: int | None = None,
) -> list[Message]:
    """Get messages for a conversation."""
    conversation = await get_conversation(session, conversation_id, user_id)
    if not conversation:
        return []

    query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )

    if limit:
        query = query.limit(limit)

    result = await session.execute(query)
    return list(result.scalars().all())


async def generate_conversation_title(
    first_message: str,
    max_length: int = 50,
) -> str:
    """Generate a conversation title from the first message using LLM."""
    # Try to use LLM for better title generation
    try:
        llm = get_llm_provider()
        prompt = (
            f"Generate a concise, descriptive title (max {max_length} characters) "
            f"for a conversation that starts with this message:\n\n"
            f"{first_message}\n\n"
            f"Title:"
        )
        response = await llm.generate(
            prompt=prompt,
            max_tokens=50,
            temperature=0.3,
        )
        title = response.content.strip()
        # Remove quotes if present
        title = title.strip('"\'')
        # Ensure it's not too long
        if len(title) > max_length:
            title = title[:max_length - 3] + "..."
        return title or "New Conversation"
    except Exception:
        # Fallback to simple truncation
        return _generate_simple_title(first_message, max_length)


def _generate_simple_title(
    first_message: str,
    max_length: int = 50,
) -> str:
    """Generate a simple conversation title from the first message (fallback)."""
    title = first_message.strip()
    if len(title) > max_length:
        title = title[:max_length - 3] + "..."
    return title or "New Conversation"


async def count_messages_for_conversations(
    session: Session,
    conversation_ids: list[UUID],
) -> dict[UUID, int]:
    """Count messages per conversation in a single query (avoids N+1)."""
    if not conversation_ids:
        return {}
    result = await session.execute(
        select(
            Message.conversation_id,
            func.count(Message.id),
        )
        .where(Message.conversation_id.in_(conversation_ids))
        .group_by(Message.conversation_id)
    )
    return {row[0]: row[1] for row in result.all()}

