"""
Demo authentication middleware and rate limiting.

Simple password gate for production demo (prevents abuse of free tier LLM APIs).
Rate limiting via slowapi (per-IP, 10 req/min on analysis endpoints).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Rate limiter instance (shared across the app)
limiter = Limiter(key_func=get_remote_address)

# Cache password at import time to avoid per-request os.environ lookups
# and eliminate TOCTOU window during env var rotation
_DEMO_PASSWORD: str = os.environ.get("DEMO_PASSWORD", "")

# Login-screen credentials (frontend login gate). Defaults keep the app
# usable out of the box; override via env vars for a real deployment.
ADMIN_USERNAME: str = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "investor2026")

_SESSION_TOKEN_TTL_SECONDS = 24 * 60 * 60


def create_session_token(username: str) -> str:
    """Issue a signed, expiring session token for the login screen."""
    expires_at = int(time.time()) + _SESSION_TOKEN_TTL_SECONDS
    payload = f"{username}:{expires_at}"
    signature = hmac.new(ADMIN_PASSWORD.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode()).decode()


def verify_session_token(token: str) -> bool:
    """Verify a session token's signature and expiry."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        username, expires_at, signature = decoded.rsplit(":", 2)
    except (ValueError, UnicodeDecodeError):
        return False

    payload = f"{username}:{expires_at}"
    expected_signature = hmac.new(
        ADMIN_PASSWORD.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return False

    return int(expires_at) >= int(time.time())


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
        "/api/eval-flywheel",
        "/api/calibration",
        "/api/replay",
        "/api/ops",
        "/api/alerts",
    )
    PUBLIC_PREFIXES = ("/api/health", "/api/explore")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        demo_password = _DEMO_PASSWORD

        # No password configured, auth gate disabled
        if not demo_password:
            return await call_next(request)

        path = request.url.path

        # Allow CORS preflight through without auth (browsers don't send
        # custom headers on OPTIONS, so X-Demo-Password won't be present)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip auth for explicitly public paths
        if any(path.startswith(prefix) for prefix in self.PUBLIC_PREFIXES):
            return await call_next(request)

        # Skip auth for non-protected paths
        if not any(path.startswith(prefix) for prefix in self.PROTECTED_PREFIXES):
            return await call_next(request)

        # Session token from the login screen is accepted as an alternative
        # to the raw demo password.
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
            if verify_session_token(token):
                return await call_next(request)

        # Check credentials (header preferred; query param accepted for EventSource
        # which cannot set custom headers in the browser API)
        provided = (
            request.headers.get("X-Demo-Password") or request.query_params.get("password") or ""
        )

        if not hmac.compare_digest(provided.encode(), demo_password.encode()):
            logger.warning(
                "Auth failed for %s %s from %s",
                request.method,
                path,
                get_remote_address(request),
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Demo password required. Add ?password=xxx or X-Demo-Password header."
                },
            )

        return await call_next(request)
