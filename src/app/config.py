from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from pydantic import field_validator
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()
