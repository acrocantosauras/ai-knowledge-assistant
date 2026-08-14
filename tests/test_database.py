import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


def test_postgresql_database_foundation_is_available() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)

    async def check_database() -> None:
        try:
            async with engine.connect() as connection:
                dialect_name = connection.engine.dialect.name
                tables = await connection.execute(
                    text(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = ANY(:table_names)
                        """
                    ),
                    {
                        "table_names": [
                            "users",
                            "documents",
                            "document_chunks",
                            "chunk_embeddings",
                            "conversations",
                            "messages",
                        ]
                    },
                )
                extension = await connection.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM pg_extension WHERE extname = 'vector'
                        )
                        """
                    )
                )
        except (ConnectionRefusedError, OSError, SQLAlchemyError) as exc:
            pytest.skip(f"PostgreSQL test database is not available: {exc}")
        finally:
            await engine.dispose()

        assert dialect_name == "postgresql"
        assert set(tables.scalars()) == {
            "users",
            "documents",
            "document_chunks",
            "chunk_embeddings",
            "conversations",
            "messages",
        }
        assert extension.scalar_one() is True

    asyncio.run(check_database())
