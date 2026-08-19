"""Tests for LLM service and providers."""


import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.llm import (
    BaseLLMProvider,
    LLMResponse,
    LLMService,
    MockProvider,
    OpenAIProvider,
    StreamingChunk,
    get_llm_provider,
    get_llm_service,
)


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_llm_response_creation(self) -> None:
        """Test LLMResponse creation with all fields."""
        response = LLMResponse(
            content="Test content",
            model="gpt-4",
            provider="openai",
            token_count=100,
            finish_reason="stop",
            metadata={"id": "test-id"},
        )
        assert response.content == "Test content"
        assert response.model == "gpt-4"
        assert response.provider == "openai"
        assert response.token_count == 100
        assert response.finish_reason == "stop"
        assert response.metadata == {"id": "test-id"}

    def test_llm_response_minimal(self) -> None:
        """Test LLMResponse with minimal fields."""
        response = LLMResponse(
            content="Test",
            model="mock",
            provider="mock",
        )
        assert response.content == "Test"
        assert response.token_count is None
        assert response.metadata is None


class TestStreamingChunk:
    """Tests for StreamingChunk dataclass."""

    def test_streaming_chunk_creation(self) -> None:
        """Test StreamingChunk creation."""
        chunk = StreamingChunk(
            content="Hello",
            is_final=False,
            token_count=1,
            finish_reason=None,
        )
        assert chunk.content == "Hello"
        assert chunk.is_final is False

    def test_streaming_chunk_final(self) -> None:
        """Test final StreamingChunk."""
        chunk = StreamingChunk(
            content="",
            is_final=True,
            finish_reason="stop",
        )
        assert chunk.content == ""
        assert chunk.is_final is True
        assert chunk.finish_reason == "stop"


class TestMockProvider:
    """Tests for MockProvider."""

    @pytest.fixture
    def mock_provider(self) -> MockProvider:
        return MockProvider()

    @pytest.mark.asyncio
    async def test_generate_basic(self, mock_provider: MockProvider) -> None:
        """Test basic text generation."""
        response = await mock_provider.generate("Hello world")
        assert isinstance(response, LLMResponse)
        assert response.provider == "mock"
        assert "Mock response to:" in response.content
        assert response.token_count is not None

    @pytest.mark.asyncio
    async def test_generate_with_context(self, mock_provider: MockProvider) -> None:
        """Test text generation with context."""
        response = await mock_provider.generate_with_context(
            system_prompt="You are helpful",
            user_message="What is AI?",
            context=["AI is artificial intelligence", "It uses machine learning"],
        )
        assert isinstance(response, LLMResponse)
        assert response.provider == "mock"
        assert "Based on 2 documents" in response.content
        assert response.metadata["context_count"] == 2

    @pytest.mark.asyncio
    async def test_generate_stream(self, mock_provider: MockProvider) -> None:
        """Test streaming text generation."""
        chunks = []
        async for chunk in mock_provider.generate_stream("Test prompt"):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert any(c.content for c in chunks)
        assert chunks[-1].is_final is True

    @pytest.mark.asyncio
    async def test_generate_with_context_stream(
        self, mock_provider: MockProvider
    ) -> None:
        """Test streaming text generation with context."""
        chunks = []
        async for chunk in mock_provider.generate_with_context_stream(
            system_prompt="You are helpful",
            user_message="What is AI?",
            context=["AI is artificial intelligence"],
        ):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert any(c.content for c in chunks)
        assert chunks[-1].is_final is True


class TestLLMService:
    """Tests for LLMService."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self) -> None:
        """Reset singleton before each test."""
        import app.services.llm as llm_module
        llm_module._llm_service = None
        yield
        llm_module._llm_service = None

    def test_get_llm_service_singleton(self) -> None:
        """Test that get_llm_service returns singleton."""
        service1 = get_llm_service()
        service2 = get_llm_service()
        assert service1 is service2

    def test_get_llm_provider(self) -> None:
        """Test getting LLM provider from service."""
        provider = get_llm_provider()
        assert isinstance(provider, BaseLLMProvider)

    @pytest.mark.asyncio
    async def test_service_generate(self) -> None:
        """Test service generate method."""
        service = get_llm_service()
        response = await service.generate("Test prompt")
        assert isinstance(response, LLMResponse)
        assert response.provider == "mock"

    @pytest.mark.asyncio
    async def test_service_generate_with_context(self) -> None:
        """Test service generate_with_context method."""
        service = get_llm_service()
        response = await service.generate_with_context(
            system_prompt="You are helpful",
            user_message="Hello",
            context=["Context 1", "Context 2"],
        )
        assert isinstance(response, LLMResponse)
        assert response.provider == "mock"

    @pytest.mark.asyncio
    async def test_service_generate_empty_prompt_raises(self) -> None:
        """Test that empty prompt raises ValueError."""
        service = get_llm_service()
        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            await service.generate("")

    @pytest.mark.asyncio
    async def test_service_generate_with_context_empty_message_raises(self) -> None:
        """Test that empty user message raises ValueError."""
        service = get_llm_service()
        with pytest.raises(ValueError, match="User message cannot be empty"):
            await service.generate_with_context("sys", "")


class TestLLMProviderSelection:
    """Tests for explicit LLM provider selection."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self) -> None:
        """Reset singleton before each test."""
        import app.services.llm as llm_module
        llm_module._llm_service = None
        yield
        llm_module._llm_service = None

    def test_mock_provider_selected(self) -> None:
        """llm_provider='mock' selects MockProvider."""
        settings = Settings(llm_provider="mock")
        import app.services.llm as llm_module
        llm_module._llm_service = None
        service = LLMService()
        service.settings = settings
        provider = service._create_provider()
        assert isinstance(provider, MockProvider)

    def test_openai_provider_selected(self) -> None:
        """llm_provider='openai' selects OpenAIProvider."""
        settings = Settings(llm_provider="openai")
        import app.services.llm as llm_module
        llm_module._llm_service = None
        service = LLMService()
        service.settings = settings
        provider = service._create_provider()
        assert isinstance(provider, OpenAIProvider)

    def test_invalid_llm_provider_rejected(self) -> None:
        """Invalid LLM provider values are rejected by settings validation."""
        with pytest.raises(ValidationError):
            Settings(llm_provider="local")

    def test_invalid_llm_provider_another_value_rejected(self) -> None:
        """An arbitrary string is rejected as LLM provider."""
        with pytest.raises(ValidationError):
            Settings(llm_provider="ollama")


class TestEmbeddingProviderStillSupportsAll:
    """Verify embedding_provider still accepts openai/local/mock."""

    @pytest.mark.parametrize(
        "provider",
        ["openai", "local", "mock"],
    )
    def test_embedding_provider_accepts_valid_values(self, provider: str) -> None:
        """embedding_provider accepts openai, local, and mock."""
        settings = Settings(embedding_provider=provider)
        assert settings.embedding_provider == provider

    def test_embedding_provider_rejects_invalid(self) -> None:
        """embedding_provider rejects unknown values."""
        with pytest.raises(ValidationError):
            Settings(embedding_provider="invalid")