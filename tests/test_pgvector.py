"""pgvector integration tests against the real PostgreSQL test database."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.config import get_settings
from app.db.models.chunk_embedding import ChunkEmbedding
from app.db.models.document import Document
from app.db.models.document_chunk import DocumentChunk
from app.db.models.user import User
from app.db.session import async_session_factory
from app.services.rag import search_similar_chunks

DIM = 4
MODEL = get_settings().embedding_model


async def _seed(session):
    user = User(email="vec@example.com", password_hash="x", display_name="v")
    session.add(user)
    await session.flush()
    doc = Document(
        user_id=user.id,
        title="d",
        source_type="upload",
        content_type="text/plain",
        status="processed",
        checksum="c",
        content="c",
        document_metadata={},
    )
    session.add(doc)
    await session.flush()
    vectors = {"near": [1, 0, 0, 0], "mid": [1, 1, 0, 0], "far": [0, 0, 0, 1]}
    chunks = {}
    for i, (name, vec) in enumerate(vectors.items()):
        chunk = DocumentChunk(
            document_id=doc.id,
            user_id=user.id,
            chunk_index=i,
            content=name,
            token_count=1,
            chunk_metadata={},
        )
        session.add(chunk)
        await session.flush()
        session.add(
            ChunkEmbedding(
                chunk_id=chunk.id,
                embedding=vec,
                embedding_model=MODEL,
                embedding_dimension=len(vec),
            )
        )
        chunks[name] = chunk
    await session.commit()
    return user, chunks


@pytest.mark.asyncio
async def test_extension_and_vector_column_exist() -> None:
    async with async_session_factory() as s:
        ext = await s.execute(
            text("SELECT extname FROM pg_extension WHERE extname='vector'")
        )
        assert ext.scalar() == "vector"
        col = await s.execute(
            text(
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_name='chunk_embeddings' AND column_name='embedding'"
            )
        )
        assert col.scalar() == "vector"


@pytest.mark.asyncio
async def test_similarity_search_ranks_by_cosine_distance() -> None:
    async with async_session_factory() as s:
        user, chunks = await _seed(s)
        found = await search_similar_chunks(s, user.id, [1, 0, 0, 0], limit=3)
        assert [c.content for c in found] == ["near", "mid", "far"]

        thresholded = await search_similar_chunks(
            s, user.id, [1, 0, 0, 0], limit=3, similarity_threshold=0.5
        )
        assert [c.content for c in thresholded] == ["near", "mid"]


@pytest.mark.asyncio
async def test_search_is_scoped_to_user() -> None:
    async with async_session_factory() as s:
        _, _ = await _seed(s)
        other = User(email="o@example.com", password_hash="x", display_name="o")
        s.add(other)
        await s.commit()
        assert await search_similar_chunks(s, other.id, [1, 0, 0, 0]) == []


@pytest.mark.asyncio
async def test_incompatible_query_dimension_returns_no_results_not_error() -> None:
    async with async_session_factory() as s:
        user, _ = await _seed(s)
        assert await search_similar_chunks(s, user.id, [1, 0, 0]) == []


@pytest.mark.asyncio
async def test_raw_dimension_mismatch_is_rejected_by_pgvector() -> None:
    """Documents the DB behaviour the dimension filter protects against."""
    async with async_session_factory() as s:
        await _seed(s)
        with pytest.raises(DBAPIError):
            await s.execute(
                text("SELECT embedding <=> CAST(:q AS vector) FROM chunk_embeddings"),
                {"q": "[1,0,0]"},
            )


def test_api_ingest_and_semantic_retrieval_with_vector_path(client, monkeypatch):
    """Upload -> embeddings stored in pgvector -> /rag/search via vector path.

    The embedder is a deterministic bag-of-words stand-in (NOT OpenAI); this
    verifies our pgvector pipeline, not the provider.
    """
    import hashlib

    from app.services.rag import EmbeddingService

    dim = get_settings().embedding_dimension

    def embed(t: str) -> list[float]:
        v = [0.0] * dim
        for w in t.lower().replace(".", " ").replace("?", " ").split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1.0
        return v

    async def fake(self, texts):
        return [embed(t) for t in texts]

    monkeypatch.setattr(EmbeddingService, "generate_embeddings", fake)
    monkeypatch.setattr(get_settings(), "embedding_provider", "openai")

    creds = {"email": "vecapi@example.com", "password": "TestPassword123!"}
    client.post("/api/v1/auth/register", json={**creds, "display_name": "v"})
    tok = client.post("/api/v1/auth/login", json=creds).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    for name, body in [
        ("fr.txt", b"Paris is the capital city of France."),
        ("cook.txt", b"Simmer the tomato sauce with basil and garlic."),
    ]:
        r = client.post(
            "/api/v1/documents/upload",
            headers=h,
            files={"file": (name, body, "text/plain")},
        )
        assert r.status_code == 201, r.text

    r = client.post(
        "/api/v1/rag/search",
        headers=h,
        json={"query": "capital of France", "limit": 2, "threshold": 0.1},
    )
    assert r.status_code == 200, r.text
    text_dump = r.text
    assert "Paris" in text_dump
    assert "tomato" not in text_dump
