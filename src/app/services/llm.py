"""LLM service with abstract provider support for question answering."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LLMResponse:
    """Response from LLM generation."""

    content: str
    model: str
    provider: str
    token_count: int | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class StreamingChunk:
    """A chunk of streaming response."""

    content: str
    is_final: bool = False
    token_count: int | None = None
    finish_reason: str | None = None


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text from a prompt."""
        ...

    @abstractmethod
    async def generate_with_context(
        self,
        system_prompt: str,
        user_message: str,
        context: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text with system prompt, context, and user message."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Generate text from a prompt as a stream of chunks."""
        ...

    @abstractmethod
    async def generate_with_context_stream(
        self,
        system_prompt: str,
        user_message: str,
        context: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Generate text with context as a stream of chunks."""
        ...


class MockProvider(BaseLLMProvider):
    """Mock LLM provider for testing."""

    async def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate mock response based on prompt."""
        await asyncio.sleep(0.01)
        response_text = f"Mock response to: {prompt[:50]}..."
        return LLMResponse(
            content=response_text,
            model=self.settings.llm_model,
            provider="mock",
            token_count=len(response_text.split()),
            finish_reason="stop",
        )

    async def generate_with_context(
        self,
        system_prompt: str,
        user_message: str,
        context: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate mock response with context."""
        await asyncio.sleep(0.01)
        if context:
            response_text = f"Based on {len(context)} documents, here is my response."
        else:
            response_text = "No relevant documents found."
        return LLMResponse(
            content=response_text,
            model=self.settings.llm_model,
            provider="mock",
            token_count=len(response_text.split()),
            finish_reason="stop",
            metadata={"context_count": len(context) if context else 0},
        )

    async def generate_stream(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Generate mock response as a stream of chunks."""
        await asyncio.sleep(0.01)
        response_text = f"Mock response to: {prompt[:50]}..."
        words = response_text.split()
        for i, word in enumerate(words):
            is_last = i == len(words) - 1
            yield StreamingChunk(
                content=word + (" " if not is_last else ""),
                is_final=is_last,
                token_count=len(words) if is_last else None,
                finish_reason="stop" if is_last else None,
            )

    async def generate_with_context_stream(
        self,
        system_prompt: str,
        user_message: str,
        context: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Generate mock response with context as a stream."""
        await asyncio.sleep(0.01)
        if context:
            response_text = f"Based on {len(context)} documents, here is my response."
        else:
            response_text = "No relevant documents found."
        words = response_text.split()
        for i, word in enumerate(words):
            is_last = i == len(words) - 1
            yield StreamingChunk(
                content=word + (" " if not is_last else ""),
                is_final=is_last,
                token_count=len(words) if is_last else None,
                finish_reason="stop" if is_last else None,
            )


class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM provider."""

    async def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text using OpenAI API."""
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError("OpenAI package not installed.") from exc

        if not self.settings.openai_api_key:
            raise RuntimeError("OpenAI API key not configured")

        client = openai.AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.llm_timeout,
        )
        response = await client.chat.completions.create(
            model=self.settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature or self.settings.llm_temperature,
            max_tokens=max_tokens or self.settings.llm_max_tokens,
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            provider="openai",
            token_count=response.usage.total_tokens if response.usage else None,
            finish_reason=choice.finish_reason,
        )

    async def generate_with_context(
        self,
        system_prompt: str,
        user_message: str,
        context: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text with context using OpenAI API."""
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError("OpenAI package not installed.") from exc

        if not self.settings.openai_api_key:
            raise RuntimeError("OpenAI API key not configured")

        client = openai.AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.llm_timeout,
        )
        messages = [{"role": "system", "content": system_prompt}]
        if context:
            ctx = "\n\n".join(
                f"[Doc {i + 1}]: {c}" for i, c in enumerate(context)
            )
            messages.append({
                "role": "user",
                "content": f"Context:\n{ctx}\n\nQuestion: {user_message}",
            })
        else:
            messages.append({"role": "user", "content": user_message})

        response = await client.chat.completions.create(
            model=self.settings.llm_model,
            messages=messages,
            temperature=temperature or self.settings.llm_temperature,
            max_tokens=max_tokens or self.settings.llm_max_tokens,
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            provider="openai",
            token_count=response.usage.total_tokens if response.usage else None,
            finish_reason=choice.finish_reason,
        )

    async def generate_stream(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Generate streaming text using OpenAI API."""
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError("OpenAI package not installed.") from exc

        if not self.settings.openai_api_key:
            raise RuntimeError("OpenAI API key not configured")

        client = openai.AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.llm_timeout,
        )
        messages = [{"role": "user", "content": prompt}]

        try:
            stream = await client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                temperature=temperature or self.settings.llm_temperature,
                max_tokens=max_tokens or self.settings.llm_max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield StreamingChunk(content=delta.content)
            yield StreamingChunk(content="", is_final=True)
        except Exception:  # noqa: BLE001
            logger.exception("OpenAI streaming failed")
            raise RuntimeError("LLM streaming failed") from None

    async def generate_with_context_stream(
        self, system_prompt: str, user_message: str, context: list[str] | None = None,
        temperature: float | None = None, max_tokens: int | None = None, **kwargs: Any,
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Generate streaming text with context using OpenAI API."""
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError("OpenAI package not installed.") from exc

        if not self.settings.openai_api_key:
            raise RuntimeError("OpenAI API key not configured")

        client = openai.AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.llm_timeout,
        )
        messages = [{"role": "system", "content": system_prompt}]
        if context:
            ctx = "\n\n".join(
                f"[Doc {i + 1}]: {c}" for i, c in enumerate(context)
            )
            messages.append({
                "role": "user",
                "content": f"Context:\n{ctx}\n\nQuestion: {user_message}",
            })
        else:
            messages.append({"role": "user", "content": user_message})

        try:
            stream = await client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                temperature=temperature or self.settings.llm_temperature,
                max_tokens=max_tokens or self.settings.llm_max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield StreamingChunk(content=delta.content)
            yield StreamingChunk(content="", is_final=True)
        except Exception:  # noqa: BLE001
            logger.exception("OpenAI streaming with context failed")
            raise RuntimeError("LLM streaming failed") from None


class LLMService:
    """LLM service that manages provider selection and generation."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._provider: BaseLLMProvider | None = None

    @property
    def provider(self) -> BaseLLMProvider:
        """Get or create the LLM provider."""
        if self._provider is None:
            self._provider = self._create_provider()
        return self._provider

    def _create_provider(self) -> BaseLLMProvider:
        """Create the appropriate LLM provider based on settings."""
        if self.settings.llm_provider == "openai":
            return OpenAIProvider()
        if self.settings.llm_provider == "mock":
            return MockProvider()
        msg = f"Unsupported LLM provider: {self.settings.llm_provider!r}"
        raise ValueError(msg)

    @property
    def model_name(self) -> str:
        """Get the configured model name."""
        return self.settings.llm_model

    @property
    def provider_name(self) -> str:
        """Get the configured provider name."""
        return self.settings.llm_provider

    async def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text from a prompt."""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        return await self.provider.generate(
            prompt, temperature, max_tokens, **kwargs
        )

    async def generate_with_context(
        self,
        system_prompt: str,
        user_message: str,
        context: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text with context."""
        if not user_message or not user_message.strip():
            raise ValueError("User message cannot be empty")
        return await self.provider.generate_with_context(
            system_prompt, user_message, context, temperature, max_tokens, **kwargs
        )

    async def generate_stream(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Generate text from a prompt as a stream."""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        async for chunk in self.provider.generate_stream(
            prompt, temperature, max_tokens, **kwargs
        ):
            yield chunk

    async def generate_with_context_stream(
        self,
        system_prompt: str,
        user_message: str,
        context: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Generate text with context as a stream."""
        if not user_message or not user_message.strip():
            raise ValueError("User message cannot be empty")
        async for chunk in self.provider.generate_with_context_stream(
            system_prompt, user_message, context, temperature, max_tokens, **kwargs
        ):
            yield chunk


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Get or create the singleton LLM service."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def get_llm_provider() -> BaseLLMProvider:
    """Get the LLM provider from the LLM service."""
    return get_llm_service().provider
