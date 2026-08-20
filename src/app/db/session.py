from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()


def get_database_url() -> str:
    if settings.environment == "test":
        return settings.test_database_url
    return settings.database_url


async_engine = create_async_engine(
    get_database_url(),
    echo=settings.database_echo,
    pool_pre_ping=True,
    poolclass=NullPool,
)

async_session_factory = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
