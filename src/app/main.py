import logging

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.config import get_settings
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(health_router)

    logger.info("Application configured", extra={"environment": settings.environment})
    return app


app = create_app()
