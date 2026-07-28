"""
Demo authentication middleware and rate limiting.

Simple password gate for production demo (prevents abuse of free tier LLM APIs).
Rate limiting via slowapi (per-IP, 10 req/min on analysis endpoints).
"""

from __future__ import annotations

import hmac
import os
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

# Rate limiter instance (shared across the app)
limiter = Limiter(key_func=get_remote_address)


class DemoAuthMiddleware(BaseHTTPMiddleware):
    """
    Simple password gate for the demo deployment.

    If DEMO_PASSWORD is set, all /api/analyze* endpoints require
    either a query param `?password=xxx` or header `X-Demo-Password: xxx`.

    Health, explore, and dashboard endpoints are always public.
    """

    PROTECTED_PREFIXES = (
        "/api/analyze",
        "/api/compare",
        "/api/chat",
        "/api/backtest",
        "/api/dashboard",
        "/api/eval",
        "/api/calibration",
    )
    PUBLIC_PREFIXES = ("/api/health", "/api/explore")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        demo_password = os.environ.get("DEMO_PASSWORD", "")

        # No password configured, auth gate disabled
        if not demo_password:
            return await call_next(request)

        path = request.url.path

        # Skip auth for explicitly public paths
        if any(path.startswith(prefix) for prefix in self.PUBLIC_PREFIXES):
            return await call_next(request)

        # Skip auth for non-protected paths
        if not any(path.startswith(prefix) for prefix in self.PROTECTED_PREFIXES):
            return await call_next(request)

        # Check credentials
        provided = (
            request.query_params.get("password") or request.headers.get("X-Demo-Password") or ""
        )

        if not hmac.compare_digest(provided.encode(), demo_password.encode()):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Demo password required. Add ?password=xxx or X-Demo-Password header."
                },
            )

        return await call_next(request)
