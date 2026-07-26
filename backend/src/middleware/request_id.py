"""
Request correlation ID middleware.

Assigns a unique ID to every request for log correlation and tracing.
The ID is available via context variable and returned in X-Request-ID header.
"""

import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.logging_config import get_logger, request_id_ctx

log = get_logger("middleware.request_id")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject a correlation ID into every request lifecycle."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Use client-provided ID if present, otherwise generate one
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        request_id_ctx.set(request_id)

        log.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            request_id=request_id,
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        log.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            request_id=request_id,
        )

        return response
