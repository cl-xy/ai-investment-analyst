"""Security response headers middleware (pure ASGI, streaming-safe)."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Headers appropriate for a JSON/SSE API backend.
# CSP on API responses is largely inert (browsers enforce CSP on documents,
# not on fetch/XHR responses), so we use a minimal deny-all policy.
SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"x-xss-protection", b"0"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (
        b"content-security-policy",
        b"default-src 'none'; frame-ancestors 'none'",
    ),
]


class SecurityHeadersMiddleware:
    """Inject security headers by intercepting http.response.start.

    Pure ASGI implementation: no buffering, no response wrapping, safe for
    SSE/StreamingResponse, and covers error responses from outer middleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Use a set of existing header names to avoid overwriting
                # route-specific headers (e.g., a custom CSP on /docs).
                existing = {h[0].lower() for h in headers}
                for name, value in SECURITY_HEADERS:
                    if name not in existing:
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
