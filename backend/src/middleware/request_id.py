"""
Request correlation ID middleware.

Assigns a unique ID to every request for log correlation and tracing.
The ID is available via context variable and returned in X-Request-ID header.
"""

import re
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.logging_config import get_logger, request_id_ctx

log = get_logger("middleware.request_id")

_VALID_REQUEST_ID = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject a correlation ID into every request lifecycle."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Use client-provided ID if present and safe, otherwise generate one
        client_id = request.headers.get("X-Request-ID")
        if client_id and _VALID_REQUEST_ID.match(client_id):
            request_id = client_id
        else:
            request_id = str(uuid.uuid4())[:8]
        request_id_ctx.set(request_id)

        log.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            request_id=request_id,
        )

        try:
            response = await call_next(request)
        except Exception:
            log.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                request_id=request_id,
                exc_info=True,
            )
            raise

        response.headers["X-Request-ID"] = request_id

        log.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            request_id=request_id,
        )

        return response
