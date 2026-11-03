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
import secrets
import time
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings

logger = logging.getLogger(__name__)

# Rate limiter instance (shared across the app)
limiter = Limiter(key_func=get_remote_address)

# Development-only fallback: tokens expire on process restart. Production
# requires a configured secret shared by every worker/machine.
_DEVELOPMENT_SIGNING_SECRET = secrets.token_urlsafe(48)

_SESSION_TOKEN_TTL_SECONDS = 24 * 60 * 60


def _signing_secret() -> str:
    if settings.session_signing_secret:
        return settings.session_signing_secret
    if settings.is_production:
        raise RuntimeError("SESSION_SIGNING_SECRET is required in production")
    return _DEVELOPMENT_SIGNING_SECRET


def create_session_token(username: str) -> str:
    """Issue a signed, expiring session token for the login screen."""
    expires_at = int(time.time()) + _SESSION_TOKEN_TTL_SECONDS
    payload = f"{username}:{expires_at}"
    signature = hmac.new(_signing_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode()).decode()


def verify_session_token(token: str) -> bool:
    """Verify a session token's signature and expiry."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        username, expires_at, signature = decoded.rsplit(":", 2)
        expiry = int(expires_at)
    except (ValueError, UnicodeDecodeError):
        return False

    payload = f"{username}:{expires_at}"
    expected_signature = hmac.new(
        _signing_secret().encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature.encode(), expected_signature.encode()):
        return False

    return username == settings.admin_username and expiry > int(time.time())


def is_authenticated(request: Request) -> bool:
    """Apply the same credential policy in middleware and sensitive routes."""
    if settings.auth_mode == "disabled":
        return True
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        if verify_session_token(authorization.removeprefix("Bearer ").strip()):
            return True
    if settings.auth_mode == "demo" and settings.demo_password:
        provided = (
            request.headers.get("X-Demo-Password") or request.query_params.get("password") or ""
        )
        return hmac.compare_digest(provided.encode(), settings.demo_password.encode())
    return False


class DemoAuthMiddleware(BaseHTTPMiddleware):
    """
    Simple password gate for the demo deployment.

    Session authentication is the default. Demo mode additionally accepts
    DEMO_PASSWORD via a header or legacy query parameter. Only explicit
    disabled mode bypasses authentication. Health and explore remain public.
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
        "/api/audit",
    )
    PUBLIC_PREFIXES = ("/api/health", "/api/explore")

    # Scheduled jobs (GitHub Actions) cannot present the demo password or a login
    # session. These POST endpoints authenticate themselves with the scheduler
    # token inside the route, so a request that carries that header is handed to
    # the route, which does the constant-time comparison and returns 401 on a bad
    # token. Exact paths only: nothing else under the protected prefixes opens up.
    SCHEDULER_POST_PATHS = frozenset(
        {
            "/api/calibration/resolve",
            "/api/eval-flywheel/runs/trigger",
        }
    )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if settings.auth_mode == "disabled":
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

        # Scheduler-token endpoints: let the route authenticate the request.
        if (
            request.method == "POST"
            and path in self.SCHEDULER_POST_PATHS
            and request.headers.get("x-scheduler-token")
        ):
            return await call_next(request)

        if not is_authenticated(request):
            logger.warning(
                "Auth failed for %s %s from %s",
                request.method,
                path,
                get_remote_address(request),
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required. Sign in to obtain a session token."},
            )

        return await call_next(request)
