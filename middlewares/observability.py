import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Injects or preserves X-Correlation-Id for request tracing."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id
        return response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Logs request method, path, status code, and duration."""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        correlation_id = getattr(request.state, "correlation_id", "n/a")
        logger.info(
            "method=%s path=%s status=%d duration_ms=%.2f correlation_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            correlation_id,
        )
        return response
