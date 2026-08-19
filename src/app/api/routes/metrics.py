"""Prometheus metrics endpoint."""

from fastapi import APIRouter, Response

from app.core.metrics import CONTENT_TYPE_LATEST, generate_metrics

router = APIRouter(tags=["system"])


@router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus metrics in text exposition format.

    Scrape this endpoint with Prometheus:
        scrape_configs:
          - job_name: ai-knowledge-assistant
            static_configs:
              - targets: ["localhost:8000"]
            metrics_path: /metrics
    """
    return Response(
        content=generate_metrics(),
        media_type=CONTENT_TYPE_LATEST,
    )
