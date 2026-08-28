"""
Watchlist-based alert subscriptions.

Portfolio positions (SQLite) are implicitly monitored by the alert pipeline.
This module covers the opt-in path: frontend watchlist tickers that aren't
necessarily portfolio positions but the user wants monitored anyway.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.db import execute, fetch, fetchrow
from src.logging_config import get_logger

log = get_logger(__name__)

DEFAULT_TRIGGER_TYPES = ["sec", "sentiment", "peer", "price"]


@dataclass(frozen=True, slots=True)
class AlertSubscription:
    ticker: str
    source: str
    trigger_types: list[str]
    active: bool


async def subscribe_ticker(
    ticker: str, trigger_types: list[str] | None = None, source: str = "watchlist"
) -> AlertSubscription:
    """Create or reactivate a subscription for `ticker`. Idempotent."""
    ticker = ticker.strip().upper()
    types = trigger_types or DEFAULT_TRIGGER_TYPES

    row = await fetchrow(
        """
        INSERT INTO alert_subscriptions (ticker, source, trigger_types, active)
        VALUES ($1, $2, $3, TRUE)
        ON CONFLICT (ticker) WHERE active = TRUE DO UPDATE SET
            trigger_types = EXCLUDED.trigger_types
        RETURNING ticker, source, trigger_types, active
        """,
        ticker,
        source,
        json.dumps(types),
    )
    if row is None:
        # Conflict target only matches active rows; if an inactive row exists
        # for this ticker, the INSERT above would violate the unique index
        # only when active — so this path means a fresh insert succeeded
        # without needing the ON CONFLICT branch. Re-fetch to be safe.
        row = await fetchrow(
            "SELECT ticker, source, trigger_types, active FROM alert_subscriptions "
            "WHERE ticker = $1 AND active = TRUE",
            ticker,
        )
    if row is None:
        # INSERT ... RETURNING should always produce a row on success, and
        # the re-fetch above covers the one known edge case. If both still
        # come back empty, something upstream is broken — fail loudly rather
        # than returning a bogus AlertSubscription.
        raise RuntimeError(f"subscribe_ticker: no row returned for ticker={ticker}")
    return AlertSubscription(
        ticker=row["ticker"],
        source=row["source"],
        trigger_types=_as_list(row["trigger_types"]),
        active=row["active"],
    )


async def unsubscribe_ticker(ticker: str) -> bool:
    """Deactivate the subscription for `ticker`. Returns True if a row was
    updated (i.e. a subscription existed)."""
    ticker = ticker.strip().upper()
    result = await execute(
        "UPDATE alert_subscriptions SET active = FALSE WHERE ticker = $1 AND active = TRUE",
        ticker,
    )
    return _affected_rows(result) > 0


async def list_subscriptions() -> list[AlertSubscription]:
    rows = await fetch(
        "SELECT ticker, source, trigger_types, active FROM alert_subscriptions "
        "WHERE active = TRUE ORDER BY ticker"
    )
    return [
        AlertSubscription(
            ticker=row["ticker"],
            source=row["source"],
            trigger_types=_as_list(row["trigger_types"]),
            active=row["active"],
        )
        for row in rows
    ]


async def get_active_subscription_tickers() -> list[str]:
    rows = await fetch("SELECT ticker FROM alert_subscriptions WHERE active = TRUE")
    return [row["ticker"] for row in rows]


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else DEFAULT_TRIGGER_TYPES
        except (json.JSONDecodeError, ValueError):
            return DEFAULT_TRIGGER_TYPES
    return DEFAULT_TRIGGER_TYPES


def _affected_rows(execute_result: str) -> int:
    """Parse asyncpg's status string (e.g. 'UPDATE 1') for the row count."""
    try:
        return int(execute_result.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0
