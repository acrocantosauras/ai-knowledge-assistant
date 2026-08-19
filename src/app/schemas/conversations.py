"""Conversation and message schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Message schemas
class MessageBase(BaseModel):
    """Base message schema."""

    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")
    token_count: int | None = Field(None, description="Token count")
    metadata: dict = Field(default_factory=dict, description="Message metadata")


class MessageCreate(MessageBase):
    """Schema for creating a message."""

    pass


class MessageResponse(MessageBase):
    """Schema for message response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


# Conversation schemas
class ConversationBase(BaseModel):
    """Base conversation schema."""

    title: str | None = Field(None, max_length=255, description="Conversation title")
    status: str = Field(default="active", description="Conversation status")
    metadata: dict = Field(default_factory=dict, description="Conversation metadata")


class ConversationCreate(BaseModel):
    """Schema for creating a conversation."""

    title: str | None = Field(None, max_length=255)
    metadata: dict = Field(default_factory=dict)


class ConversationUpdate(BaseModel):
    """Schema for updating a conversation."""

    title: str | None = Field(None, max_length=255)
    status: str | None = Field(None)
    metadata: dict | None = Field(None)


class ConversationResponse(ConversationBase):
    """Schema for conversation response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    message_count: int | None = Field(None, description="Number of messages")


class ConversationWithMessages(ConversationResponse):
    """Schema for conversation with messages."""

    messages: list[MessageResponse] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    """Schema for listing conversations."""

    conversations: list[ConversationResponse]
    total: int
    limit: int
    offset: int
