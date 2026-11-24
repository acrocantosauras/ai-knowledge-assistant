"""Prometheus metrics endpoint (bearer-token protected when configured)."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.config import Settings, get_settings
from app.core.metrics import CONTENT_TYPE_LATEST, generate_metrics

router = APIRouter(tags=["system"])


def _require_metrics_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Enforce `Authorization: Bearer <APP_METRICS_TOKEN>` when a token is set.

    Production requires a token (see config validation). In development and
    test the endpoint stays open when no token is configured.
    """
    expected = settings.metrics_token
    if not expected:
        return
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        supplied.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/metrics", dependencies=[Depends(_require_metrics_token)])
async def metrics() -> Response:
    """Expose Prometheus metrics in text exposition format.

    Prometheus scrape config:
        scrape_configs:
          - job_name: ai-knowledge-assistant
            metrics_path: /metrics
            authorization:
              credentials_file: /etc/prometheus/metrics_token
            static_configs:
              - targets: ["api:8000"]
    """
    return Response(
        content=generate_metrics(),
        media_type=CONTENT_TYPE_LATEST,
    )
