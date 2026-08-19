"""Health check endpoints.

- GET /health        — Liveness probe (always 200 if app is running)
- GET /health/ready  — Readiness probe (verifies database connectivity)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Liveness probe — confirms the application process is running."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    """Readiness probe — verifies the app can serve requests.

    Checks:
      1. Application is configured
      2. Database is reachable and responsive
      3. Redis is reachable (if configured)
    """
    checks: dict[str, str | dict[str, str]] = {}
    all_ok = True

    # --- Database check ---
    try:
        result = await session.execute(text("SELECT 1"))
        result.scalar()
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001
        logger.exception("Readiness check: database unreachable")
        # Never expose raw exception details — they may contain
        # connection strings, hostnames, or credentials.
        checks["database"] = "error: connection failed"
        all_ok = False

    # --- Redis check (only if configured) ---
    from app.core.redis import check_redis_health, is_redis_configured

    if is_redis_configured():
        redis_health = await check_redis_health()
        if redis_health["status"] == "ok":
            checks["redis"] = "ok"
        elif redis_health["status"] == "skipped":
            checks["redis"] = "skipped"
        else:
            # Never expose raw error details from Redis
            logger.warning(
                "Readiness check: Redis unreachable: %s",
                redis_health.get("error", "unknown"),
            )
            checks["redis"] = "error: connection failed"
            all_ok = False

    response_status = (
        status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return JSONResponse(
        status_code=response_status,
        content={
            "status": "ok" if all_ok else "degraded",
            "service": settings.app_name,
            "environment": settings.environment,
            "checks": checks,
        },
    )
