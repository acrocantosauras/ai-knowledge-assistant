"""User preferences schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserPreferences(BaseModel):
    """User preferences model."""

    model_config = ConfigDict(extra="allow")

    # LLM settings
    default_model: str | None = Field(
        default=None, description="Default LLM model to use"
    )
    default_temperature: float | None = Field(
        default=None, ge=0.0, le=2.0, description="Default temperature for LLM"
    )
    default_max_tokens: int | None = Field(
        default=None, ge=1, le=4096, description="Default max tokens for LLM"
    )

    # RAG settings
    default_rag_limit: int | None = Field(
        default=None, ge=1, le=50, description="Default number of documents to retrieve"
    )
    default_rag_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Default similarity threshold"
    )

    # UI settings
    theme: str | None = Field(default=None, description="UI theme preference")
    language: str | None = Field(default=None, description="Preferred language")

    # Custom preferences
    custom: dict[str, Any] | None = Field(
        default=None, description="Custom user preferences"
    )


class UserPreferencesResponse(UserPreferences):
    """User preferences response model."""
    pass


class UserPreferencesUpdate(BaseModel):
    """User preferences update request model."""

    model_config = ConfigDict(extra="allow")

    default_model: str | None = Field(
        default=None, description="Default LLM model to use"
    )
    default_temperature: float | None = Field(
        default=None, ge=0.0, le=2.0, description="Default temperature for LLM"
    )
    default_max_tokens: int | None = Field(
        default=None, ge=1, le=4096, description="Default max tokens for LLM"
    )
    default_rag_limit: int | None = Field(
        default=None, ge=1, le=50, description="Default number of documents to retrieve"
    )
    default_rag_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Default similarity threshold"
    )
    theme: str | None = Field(default=None, description="UI theme preference")
    language: str | None = Field(default=None, description="Preferred language")
    custom: dict[str, Any] | None = Field(
        default=None, description="Custom user preferences"
    )


class UserProfileResponse(BaseModel):
    """User profile response model including preferences."""
    id: str
    email: str
    display_name: str | None
    is_active: bool
    preferences: UserPreferencesResponse

    model_config = ConfigDict(from_attributes=True)