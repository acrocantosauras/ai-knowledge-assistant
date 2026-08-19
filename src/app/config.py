from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_NAME = "ai-knowledge-assistant"


def get_app_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.1.0"


class Settings(BaseSettings):
    app_name: str = "AI Knowledge Assistant"
    app_version: str = get_app_version()
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = (
        "postgresql+asyncpg://ai_knowledge_user:ai_knowledge_password"
        "@localhost:5432/ai_knowledge_assistant"
    )
    test_database_url: str = (
        "postgresql+asyncpg://ai_knowledge_user:ai_knowledge_password"
        "@localhost:5432/ai_knowledge_assistant_test"
    )
    database_echo: bool = False
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Embedding configuration
    embedding_provider: Literal["openai", "local", "mock"] = "mock"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    openai_api_key: str = ""
    local_embedding_model_path: str = ""

    # Chunking configuration
    chunk_size: int = 500
    chunk_overlap: int = 100

    # LLM configuration
    llm_provider: Literal["openai", "local", "mock"] = "mock"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 1024
    llm_timeout: int = 60

    # CORS configuration
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Rate limiting
    rate_limit_default: str = "60/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_upload: str = "20/hour"
    rate_limit_rag: str = "30/minute"
    rate_limit_qa: str = "20/minute"

    # Redis (optional — used for rate limiting storage and caching)
    redis_url: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_config(self) -> "Settings":
        """Enforce security requirements in production/staging environments."""
        if self.environment in ("production", "staging"):
            if not self.jwt_secret_key:
                raise ValueError(
                    "APP_JWT_SECRET_KEY is required in production."
                    " Generate: python -c 'import secrets;"
                    " print(secrets.token_urlsafe(64))'"
                )
            if self.jwt_secret_key == "change-me-to-a-random-secret-key":
                raise ValueError(
                    "APP_JWT_SECRET_KEY must not be the default"
                    " value in production."
                    " Generate: python -c 'import secrets;"
                    " print(secrets.token_urlsafe(64))'"
                )
            if (
                self.embedding_provider == "openai"
                and not self.openai_api_key
            ):
                raise ValueError(
                    "APP_OPENAI_API_KEY is required when"
                    " APP_EMBEDDING_PROVIDER=openai"
                )
            if (
                self.llm_provider == "openai"
                and not self.openai_api_key
            ):
                raise ValueError(
                    "APP_OPENAI_API_KEY is required when"
                    " APP_LLM_PROVIDER=openai"
                )
        return self

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_test_settings() -> Settings:
    return Settings(environment="test")
