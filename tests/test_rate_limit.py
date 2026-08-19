"""Tests for rate limiting middleware."""

from app.config import Settings
from app.core.rate_limit import _create_limiter, _NoOpLimiter, limiter


def test_rate_limiter_is_noop_in_test_environment() -> None:
    """Rate limiter should be a no-op when APP_ENVIRONMENT=test."""
    assert isinstance(limiter, _NoOpLimiter)


def test_noop_limiter_limit_returns_function_unchanged() -> None:
    """The no-op limiter's limit decorator should return the function as-is."""
    noop = _NoOpLimiter()

    def my_view():
        return "hello"

    decorated = noop.limit("10/minute")(my_view)
    assert decorated is my_view
    assert decorated() == "hello"


def test_noop_limiter_exempt_returns_function_unchanged() -> None:
    """The no-op limiter's exempt should return the function as-is."""
    noop = _NoOpLimiter()

    def my_view():
        return "hello"

    exempted = noop.exempt(my_view)
    assert exempted is my_view


def test_live_limiter_created_in_development() -> None:
    """In development mode, a real Limiter should be created."""
    from slowapi import Limiter

    settings = Settings(environment="development")
    # The module-level limiter is created at import time, so we test
    # the factory function directly with a controlled settings object.
    import app.core.rate_limit as rl

    original = rl.get_settings
    rl.get_settings = lambda: settings
    try:
        created = _create_limiter()
        assert isinstance(created, Limiter)
    finally:
        rl.get_settings = original
