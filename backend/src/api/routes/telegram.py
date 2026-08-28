"""
Telegram webhook route.

Not gated by DemoAuthMiddleware's password check (Telegram's servers can't
supply it) — instead validated via the X-Telegram-Bot-Api-Secret-Token
header that Telegram echoes back on every webhook call, per their
recommended webhook security model.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from src.alerts.telegram import handle_update, validate_webhook_secret
from src.logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["telegram"])


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if not validate_webhook_secret(x_telegram_bot_api_secret_token):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid update payload") from None

    try:
        await handle_update(update)
    except Exception:
        # Telegram retries on non-2xx; log and ack anyway so a single bad
        # update doesn't cause Telegram to hammer the webhook with retries.
        log.exception("telegram_webhook_handler_failed")

    return {"ok": True}
