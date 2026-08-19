import asyncio
import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

os.environ["APP_ENVIRONMENT"] = "test"
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import models as _models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.main import create_app  # noqa: E402


def _create_test_engine() -> AsyncEngine:
    """Create an engine bound to the test database.

    NullPool is critical: the fixture runs in its own event loop via
    asyncio.run(), and any pooled asyncpg connection would outlive that
    loop and break on Windows with 'Event loop is closed' errors.
    """
    settings = get_settings()
    return create_async_engine(
        settings.test_database_url,
        pool_pre_ping=True,
        poolclass=NullPool,
    )


def _reset_database() -> None:
    """Drop and recreate all tables in the test database.

    Runs in a dedicated event loop; every connection is created and torn
    down within that loop because NullPool holds no connections.
    """
    engine = _create_test_engine()

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    try:
        asyncio.run(prepare())
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture(autouse=True)
def reset_database() -> Generator[None, None, None]:
    _reset_database()
    yield
    _reset_database()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(create_app()) as test_client:
        yield test_client
