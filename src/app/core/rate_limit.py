"""Rate limiting middleware and dependencies.

Uses slowapi with an in-memory store. Configure limits via APP_*_RATE_LIMIT
environment variables (e.g. APP_RATE_LIMIT_DEFAULT="60/minute").

Rate limiting is completely disabled when APP_ENVIRONMENT=test.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config import get_settings


def _get_client_ip(request):
    """Extract client IP, respecting X-Forwarded-For behind proxies."""
    return get_remote_address(request)


def _create_limiter():
    """Create the limiter, disabled in test environment."""
    settings = get_settings()
    if settings.environment == "test":
        return _NoOpLimiter()

    # Use Redis storage if configured, otherwise in-memory
    from app.core.redis import is_redis_configured

    storage = "memory://"
    if is_redis_configured():
        storage = settings.redis_url
        import logging

        logging.getLogger(__name__).info("Rate limiter using Redis storage")

    return Limiter(
        key_func=_get_client_ip,
        default_limits=[settings.rate_limit_default],
        storage_uri=storage,
    )


class _NoOpLimiter:
    """A rate limiter that does nothing — used in test environments."""

    def limit(self, *args, **kwargs):  # noqa: ARG002
        def decorator(func):
            return func

        return decorator

    def exempt(self, func):  # noqa: ARG002
        return func


limiter = _create_limiter()


def setup_rate_limiting(app):
    """Attach rate limiting middleware and exception handler to the app."""
    settings = get_settings()

    # Skip rate limiting in test environment
    if settings.environment == "test":
        return

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)


async def _rate_limit_exceeded_handler(request, exc):
    """Return a 429 JSON response when rate limit is exceeded."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "retry_after": getattr(exc, "retry_after", None),
        },
    )
