"""
Alerts API routes.

Covers both the in-app alert feed (history, unread count, acknowledge) and
watchlist-based alert subscriptions (opt-in monitoring for tickers that
aren't necessarily portfolio positions).

Gated by DemoAuthMiddleware like the other user-facing routes (dashboard,
calibration, etc.) — added to PROTECTED_PREFIXES.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from src.alerts.subscriptions import (
    list_subscriptions,
    subscribe_ticker,
    unsubscribe_ticker,
)
from src.alerts.telegram import get_active_chat_ids
from src.db import fetch, fetchval

from ..schemas import (
    AlertItem,
    AlertListResponse,
    SubscriptionItem,
    SubscriptionListResponse,
    SubscriptionRequest,
    TelegramStatusResponse,
    UnreadCountResponse,
)

router = APIRouter(tags=["alerts"])


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _row_to_alert_item(row) -> AlertItem:
    return AlertItem(
        id=str(row["id"]),
        ticker=row["ticker"],
        alert_type=row["alert_type"],
        severity=row["severity"],
        drift_score=row["drift_score"],
        old_signal=row["old_signal"],
        new_signal=row["new_signal"],
        reasoning_diff=_as_dict(row["reasoning_diff"]),
        triggered_by=_as_list(row["triggered_by"]),
        llm_judged=row["llm_judged"],
        dispatched_telegram=row["dispatched_telegram"],
        created_at=row["created_at"],
        acknowledged_at=row["acknowledged_at"],
    )


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ticker: str | None = Query(default=None),
) -> AlertListResponse:
    """Paginated alert history, newest first. Optionally filtered by ticker."""
    if ticker:
        ticker = ticker.strip().upper()
        rows = await fetch(
            "SELECT * FROM alerts WHERE ticker = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            ticker,
            limit,
            offset,
        )
        total = await fetchval("SELECT COUNT(*) FROM alerts WHERE ticker = $1", ticker)
    else:
        rows = await fetch(
            "SELECT * FROM alerts ORDER BY created_at DESC LIMIT $1 OFFSET $2", limit, offset
        )
        total = await fetchval("SELECT COUNT(*) FROM alerts")

    return AlertListResponse(alerts=[_row_to_alert_item(r) for r in rows], total=total or 0)


@router.get("/alerts/unread-count", response_model=UnreadCountResponse)
async def unread_count() -> UnreadCountResponse:
    count = await fetchval("SELECT COUNT(*) FROM alerts WHERE acknowledged_at IS NULL")
    return UnreadCountResponse(unread_count=count or 0)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertItem)
async def acknowledge_alert(alert_id: str) -> AlertItem:
    try:
        aid = uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert ID") from None

    row = await fetch(
        """
        UPDATE alerts SET acknowledged_at = $2
        WHERE id = $1 AND acknowledged_at IS NULL
        RETURNING *
        """,
        aid,
        datetime.now(timezone.utc),
    )
    if not row:
        existing = await fetch("SELECT * FROM alerts WHERE id = $1", aid)
        if not existing:
            raise HTTPException(status_code=404, detail="Alert not found")
        return _row_to_alert_item(existing[0])

    return _row_to_alert_item(row[0])


# --- Watchlist-based alert subscriptions ---


@router.get("/alerts/telegram/status", response_model=TelegramStatusResponse)
async def telegram_status() -> TelegramStatusResponse:
    """Whether any Telegram chat is currently registered for alert delivery.

    No per-browser-session ↔ chat_id linkage exists (single-bot, no user
    accounts) so this reflects aggregate connection state, not "this
    specific visitor." See TelegramStatusResponse docstring.
    """
    chat_ids = await get_active_chat_ids()
    return TelegramStatusResponse(connected=len(chat_ids) > 0, active_chat_count=len(chat_ids))


@router.get("/alerts/subscriptions", response_model=SubscriptionListResponse)
async def get_subscriptions() -> SubscriptionListResponse:
    subs = await list_subscriptions()
    return SubscriptionListResponse(
        subscriptions=[
            SubscriptionItem(
                ticker=s.ticker, source=s.source, trigger_types=s.trigger_types, active=s.active
            )
            for s in subs
        ]
    )


@router.post("/alerts/subscribe", response_model=SubscriptionItem)
async def create_subscription(payload: SubscriptionRequest) -> SubscriptionItem:
    sub = await subscribe_ticker(payload.ticker, payload.trigger_types)
    return SubscriptionItem(
        ticker=sub.ticker, source=sub.source, trigger_types=sub.trigger_types, active=sub.active
    )


@router.delete("/alerts/subscribe/{ticker}", status_code=204)
async def delete_subscription(ticker: str) -> None:
    removed = await unsubscribe_ticker(ticker)
    if not removed:
        raise HTTPException(status_code=404, detail=f"No active subscription for {ticker.upper()}")
