"""Prometheus metrics for monitoring.

Provides:
  - HTTP request metrics (latency, status codes, in-flight)
  - Application metrics (documents, conversations, LLM calls)
  - Middleware to automatically instrument all requests
"""

from __future__ import annotations

import time
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Re-export for use by other modules
CONTENT_TYPE_LATEST = CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY = CollectorRegistry()

try:
    import os

    if "PROMETHEUS_MULTIPROC_DIR" in os:
        REGISTRY = CollectorRegistry()
        multiprocess.MultiProcessCollector(REGISTRY)
except Exception:  # noqa: BLE001
    pass


# ---------------------------------------------------------------------------
# HTTP request metrics
# ---------------------------------------------------------------------------

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(
        0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5,
        0.75, 1.0, 2.5, 5.0, 10.0,
    ),
    registry=REGISTRY,
)

HTTP_REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Number of HTTP requests currently being processed",
    registry=REGISTRY,
)


# ---------------------------------------------------------------------------
# Application metrics
# ---------------------------------------------------------------------------

DOCUMENTS_UPLOADED_TOTAL = Counter(
    "documents_uploaded_total",
    "Total documents uploaded",
    ["user_id"],
    registry=REGISTRY,
)

CONVERSATIONS_CREATED_TOTAL = Counter(
    "conversations_created_total",
    "Total conversations created",
    ["user_id"],
    registry=REGISTRY,
)

QA_QUESTIONS_TOTAL = Counter(
    "qa_questions_total",
    "Total QA questions asked",
    ["provider"],
    registry=REGISTRY,
)

QA_LATENCY_SECONDS = Histogram(
    "qa_latency_seconds",
    "QA response latency in seconds",
    ["provider"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)

RAG_SEARCH_TOTAL = Counter(
    "rag_search_total",
    "Total RAG search requests",
    registry=REGISTRY,
)

RAG_CHUNKS_RETURNED = Histogram(
    "rag_chunks_returned",
    "Number of chunks returned per RAG search",
    buckets=(0, 1, 2, 3, 5, 10, 20),
    registry=REGISTRY,
)

ACTIVE_USERS = Gauge(
    "active_users",
    "Number of active users",
    registry=REGISTRY,
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def _normalise_path(request: Request) -> str:
    """Collapse path parameters into placeholders for low-cardinality labels.

    /api/v1/documents/550e8400-e29b-...  ->  /api/v1/documents/{id}
    /api/v1/conversations/abc/messages   ->  /api/v1/conversations/{id}/messages
    """
    path = request.url.path
    segments = path.split("/")
    normalised: list[str] = []
    for seg in segments:
        if not seg:
            continue
        # UUID-like or purely numeric segments are path params
        if len(seg) > 36 or (seg.count("-") >= 4):
            normalised.append("{id}")
        elif seg.isdigit():
            normalised.append("{id}")
        else:
            normalised.append(seg)
    return "/" + "/".join(normalised)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware that records request count, latency, and in-flight gauges."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Skip the metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)

        HTTP_REQUESTS_IN_FLIGHT.inc()
        start = time.monotonic()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:  # noqa: BLE001
            status_code = 500
            raise
        finally:
            elapsed = time.monotonic() - start
            endpoint = _normalise_path(request)
            method = request.method

            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, status=str(status_code)
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, endpoint=endpoint
            ).observe(elapsed)
            HTTP_REQUESTS_IN_FLIGHT.dec()


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def generate_metrics() -> bytes:
    """Serialise all metrics in Prometheus text exposition format."""
    return generate_latest(REGISTRY)
