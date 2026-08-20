import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routes.auth import router as auth_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.qa import router as qa_router
from app.api.routes.rag import router as rag_router
from app.api.routes.users import router as users_router
from app.config import get_settings
from app.core.metrics import PrometheusMiddleware
from app.core.rate_limit import setup_rate_limiting
from app.core.redis import (
    check_redis_health,
    close_redis_client,
    is_redis_configured,
)
from app.db.session import async_session_factory
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

# Maximum number of retries when waiting for the database on startup.
_DB_STARTUP_RETRIES = 10
_DB_STARTUP_RETRY_DELAY = 2  # seconds between retries


async def _verify_database_connection() -> None:
    """Ping the database and raise on failure after retries are exhausted.

    Called once during application startup so the process fails fast if
    the database is unreachable rather than silently serving 500s.
    """
    import asyncio

    last_error: Exception | None = None

    for attempt in range(1, _DB_STARTUP_RETRIES + 1):
        try:
            async with async_session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar()
            logger.info(
                "Database connection verified",
                extra={"attempt": attempt},
            )
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            # Do NOT log the raw exception — it may contain connection
            # strings, hostnames, or credentials.
            logger.warning(
                "Database connection attempt %d/%d failed",
                attempt,
                _DB_STARTUP_RETRIES,
            )
            if attempt < _DB_STARTUP_RETRIES:
                await asyncio.sleep(_DB_STARTUP_RETRY_DELAY)

    # All retries exhausted — hard fail so the container orchestrator
    # (Docker / k8s) can restart the process.
    logger.critical(
        "Could not connect to database after %d attempts",
        _DB_STARTUP_RETRIES,
    )
    raise RuntimeError(
        f"Database unavailable after {_DB_STARTUP_RETRIES} retries"
    ) from last_error


async def _verify_redis_connection() -> None:
    """Ping Redis if configured. Logs a warning but does not hard-fail."""
    if not is_redis_configured():
        return

    health = await check_redis_health()
    if health["status"] == "ok":
        logger.info(
            "Redis connection verified",
            extra={"latency_ms": health.get("latency_ms")},
        )
    else:
        # Redis is optional — warn but don't crash
        logger.warning(
            "Redis connection check failed: %s",
            health.get("error", "unknown"),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown events."""
    # --- Startup ---
    settings = get_settings()
    logger.info(
        "Starting application",
        extra={"environment": settings.environment},
    )

    # Verify database connectivity (hard fail if unreachable)
    await _verify_database_connection()

    # Verify Redis connectivity (soft fail — warn only)
    await _verify_redis_connection()

    logger.info("Application startup complete")

    yield

    # --- Shutdown ---
    logger.info("Shutting down application")
    if is_redis_configured():
        await close_redis_client()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    # Middleware (order matters — first added = outermost)
    setup_rate_limiting(app)
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(conversations_router, prefix="/api/v1")
    app.include_router(qa_router, prefix="/api/v1")
    app.include_router(rag_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")

    # Global exception handler — prevents raw stack traces from
    # leaking to API clients for truly unexpected errors.
    _global_logger = logging.getLogger(__name__)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        _global_logger.exception(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # Serve frontend static files if they exist.
    # Vite generates absolute asset paths (/assets/...), so the assets
    # directory must be mounted at the root — not under /static.
    # In Docker the package is installed site-wide, so the relative path
    # from __file__ doesn't point to /app/static.  Try the project-root
    # path first (local dev), fall back to /app/static (container).
    static_dir = Path(__file__).parent.parent.parent / "static"
    if not static_dir.is_dir():
        static_dir = Path("/app/static")
    if static_dir.is_dir():
        from fastapi.responses import FileResponse

        # Serve JS/CSS assets
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="static-assets",
            )

        # Serve favicon and icons
        for icon_name in ("favicon.svg", "icons.svg"):
            icon_path = static_dir / icon_name
            if icon_path.is_file():

                def _make_icon_response(p: Path = icon_path) -> FileResponse:
                    return FileResponse(str(p))

                app.add_api_route(
                    f"/{icon_name}",
                    _make_icon_response,
                    methods=["GET"],
                    include_in_schema=False,
                )

        # SPA fallback — serve index.html for all unmatched routes so
        # that client-side routing (React Router) works correctly.
        index_file = static_dir / "index.html"
        if index_file.is_file():

            async def _spa_fallback() -> FileResponse:
                return FileResponse(str(index_file))

            app.add_api_route(
                "/{full_path:path}",
                _spa_fallback,
                methods=["GET"],
                include_in_schema=False,
            )

    return app


app = create_app()
