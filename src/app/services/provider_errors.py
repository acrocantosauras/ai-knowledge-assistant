"""Translate upstream provider (OpenAI) failures into safe API errors."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """An upstream AI provider failed. `public_detail` is safe to show clients."""

    def __init__(self, status_code: int, public_detail: str) -> None:
        super().__init__(public_detail)
        self.status_code = status_code
        self.public_detail = public_detail


def translate_openai_error(exc: Exception) -> ProviderError | None:
    """Map an openai SDK exception to a ProviderError, or None if not one."""
    try:
        import openai
    except ImportError:  # pragma: no cover
        return None

    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        # Operator misconfiguration: log class only, never the key or body.
        logger.error("OpenAI rejected credentials (%s)", type(exc).__name__)
        return ProviderError(502, "AI provider is misconfigured.")
    if isinstance(exc, openai.RateLimitError):
        logger.warning("OpenAI rate limit / quota exceeded")
        return ProviderError(429, "AI provider rate limit reached. Retry later.")
    if isinstance(exc, openai.APITimeoutError):
        logger.warning("OpenAI request timed out")
        return ProviderError(504, "AI provider timed out.")
    if isinstance(exc, openai.APIError):
        logger.error("OpenAI API error (%s)", type(exc).__name__)
        return ProviderError(502, "AI provider request failed.")
    return None
