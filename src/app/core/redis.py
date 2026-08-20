"""Async Redis client with connection pooling.

Provides a singleton Redis client used for:
  - Rate limiting storage (via slowapi)
  - Caching (available for future use)
  - Health checks (readiness probe)

When APP_REDIS_URL is empty, Redis is disabled and all operations
are gracefully skipped.
"""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None


def get_redis_url() -> str:
    """Return the configured Redis URL, or empty string if disabled."""
    return get_settings().redis_url


def _mask_url(url: str) -> str:
    """Redact credentials from a Redis URL for safe logging."""
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        if parsed.password:
            return urlunparse(
                parsed._replace(
                    netloc=parsed.netloc.replace(f":{parsed.password}@", ":***@")
                )
            )
    except Exception:  # noqa: BLE001
        pass
    return url


def is_redis_configured() -> bool:
    """Return True if a non-empty Redis URL is configured."""
    return bool(get_redis_url())


async def get_redis_client() -> aioredis.Redis | None:
    """Get or create the singleton async Redis client.

    Returns None if Redis is not configured.
    """
    global _redis_client
    if not is_redis_configured():
        return None

    if _redis_client is None:
        url = get_redis_url()
        _redis_client = aioredis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        logger.info("Redis client created", extra={"url": _mask_url(url)})
    return _redis_client


async def close_redis_client() -> None:
    """Close the Redis connection pool. Call on app shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis client closed")


async def check_redis_health() -> dict[str, Any]:
    """Ping Redis and return health status.

    Returns:
        {"status": "ok", "latency_ms": float} on success
        {"status": "error", "error": str} on failure
        {"status": "skipped"} if Redis is not configured
    """
    if not is_redis_configured():
        return {"status": "skipped"}

    client = await get_redis_client()
    if client is None:
        return {"status": "skipped"}

    try:
        import time

        start = time.monotonic()
        await client.ping()
        latency_ms = (time.monotonic() - start) * 1000
        return {"status": "ok", "latency_ms": round(latency_ms, 2)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
