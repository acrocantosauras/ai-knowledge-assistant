from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models.chunk_embedding import ChunkEmbedding
from app.db.models.document import Document
from app.db.models.document_chunk import DocumentChunk


@dataclass(slots=True)
class ChunkingConfig:
    chunk_size: int = 500
    overlap: int = 100


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    if not text:
        return []

    chunks: list[str] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end]
        chunks.append(chunk)
        if end == text_length:
            break
        start += chunk_size - overlap
    return chunks


async def create_document_chunks(
    session: AsyncSession,
    document: Document,
    text: str,
    config: ChunkingConfig | None = None,
) -> list[DocumentChunk]:
    chunk_config = config or ChunkingConfig()
    chunks = chunk_text(text, chunk_config.chunk_size, chunk_config.overlap)
    created: list[DocumentChunk] = []
    for index, chunk in enumerate(chunks):
        item = DocumentChunk(
            document_id=document.id,
            user_id=document.user_id,
            chunk_index=index,
            content=chunk,
            token_count=max(1, len(chunk.split())),
            chunk_metadata={
                "source": document.title,
                "chunk_size": chunk_config.chunk_size,
                "overlap": chunk_config.overlap,
            },
        )
        session.add(item)
        created.append(item)
    await session.commit()
    for item in created:
        await session.refresh(item)
    return created


async def search_document_chunks(
    session: AsyncSession,
    user_id: Any,
    query: str,
    limit: int = 5,
) -> list[DocumentChunk]:
    if not query.strip():
        return []

    query_lower = query.lower()
    result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.user_id == user_id)
        .where(DocumentChunk.content.ilike(f"%{query_lower}%"))
        .order_by(DocumentChunk.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


class EmbeddingService:
    """Abstract embedding service with multiple provider support."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._dimension = self.settings.embedding_dimension
        self._model_name = self.settings.embedding_model

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        provider = self.settings.embedding_provider
        if provider == "openai":
            return await self._generate_openai_embeddings(texts)
        elif provider == "local":
            return await self._generate_local_embeddings(texts)
        else:  # mock
            return await self._generate_mock_embeddings(texts)

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        embeddings = await self.generate_embeddings([text])
        return embeddings[0]

    async def _generate_openai_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using OpenAI API."""
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI package not installed. Install with 'pip install openai'."
            ) from exc

        if not self.settings.openai_api_key:
            raise RuntimeError("OpenAI API key not configured")

        client = openai.AsyncOpenAI(api_key=self.settings.openai_api_key)
        response = await client.embeddings.create(
            model=self.settings.embedding_model,
            input=texts,
        )
        return [data.embedding for data in response.data]

    async def _generate_local_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using a local model."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers not installed. "
                "Install with 'pip install sentence-transformers'."
            ) from exc

        if not self.settings.local_embedding_model_path:
            raise RuntimeError("Local embedding model path not configured")

        model = SentenceTransformer(self.settings.local_embedding_model_path)
        embeddings = model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    async def _generate_mock_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic mock embeddings for testing."""
        embeddings = []
        for text_content in texts:
            text_hash = hashlib.sha256(text_content.encode()).digest()
            embedding = []
            for i in range(self._dimension):
                byte_idx = i % len(text_hash)
                val = (text_hash[byte_idx] / 255.0) * 2 - 1
                embedding.append(val)
            embeddings.append(embedding)
        return embeddings


_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the singleton embedding service."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


async def create_embeddings_for_chunks(
    session: AsyncSession,
    chunks: list[DocumentChunk],
    embedding_service: EmbeddingService | None = None,
) -> list[ChunkEmbedding]:
    """Create embeddings for document chunks and store them."""
    service = embedding_service or get_embedding_service()

    texts = [chunk.content for chunk in chunks]
    embeddings = await service.generate_embeddings(texts)

    created: list[ChunkEmbedding] = []
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        emb = ChunkEmbedding(
            chunk_id=chunk.id,
            embedding=embedding,
            embedding_model=service.model_name,
            embedding_dimension=service.dimension,
        )
        session.add(emb)
        created.append(emb)

    await session.commit()
    for item in created:
        await session.refresh(item)
    return created


async def search_similar_chunks(
    session: AsyncSession,
    user_id: Any,
    query_embedding: list[float],
    limit: int = 5,
    similarity_threshold: float = 0.0,
) -> list[DocumentChunk]:
    """Search for document chunks using pgvector cosine similarity."""
    if not query_embedding:
        return []

    result = await session.execute(
        select(DocumentChunk)
        .join(ChunkEmbedding, DocumentChunk.id == ChunkEmbedding.chunk_id)
        .where(DocumentChunk.user_id == user_id)
        .where(ChunkEmbedding.embedding_model == get_settings().embedding_model)
        .where(
            text("1 - (chunk_embeddings.embedding <=> :query_embedding) >= :threshold")
        )
        .options(selectinload(DocumentChunk.document))
        .order_by(text("chunk_embeddings.embedding <=> :query_embedding"))
        .limit(limit)
        .params(
            query_embedding=query_embedding,
            threshold=similarity_threshold,
        )
    )
    return list(result.scalars().all())


async def search_document_chunks_with_embeddings(
    session: AsyncSession,
    user_id: Any,
    query: str,
    limit: int = 5,
    threshold: float = 0.7,
    use_embeddings: bool = True,
) -> list[DocumentChunk]:
    """Search for document chunks using embeddings or text fallback."""
    if not query.strip():
        return []

    settings = get_settings()

    if use_embeddings and settings.embedding_provider != "mock":
        embedding_service = get_embedding_service()
        query_embedding = await embedding_service.generate_embedding(query)
        return await search_similar_chunks(
            session,
            user_id,
            query_embedding,
            limit,
            similarity_threshold=threshold,
        )

    # Fallback to text-based search
    query_lower = query.lower()
    result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.user_id == user_id)
        .where(DocumentChunk.content.ilike(f"%{query_lower}%"))
        .options(selectinload(DocumentChunk.document))
        .order_by(DocumentChunk.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
