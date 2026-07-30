"""
Provider daily budget tracking. PostgreSQL-backed.

Prevents exceeding free-tier rate limits on external APIs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.db import fetchrow

# Conservative daily limits (leave headroom for manual use)
DAILY_LIMITS: dict[str, int] = {
    "alpha_vantage": 20,
    "newsapi": 90,
    "openrouter": 1400,
    # StockTwits' public symbol-stream endpoint requires no API key, so there's
    # no documented per-key quota to size against — this is a deliberately
    # conservative guess pending real usage data, not a verified provider limit.
    "stocktwits": 300,
}


async def check_budget(provider: str) -> bool:
    """Return True if the provider has remaining budget for today (advisory, not atomic)."""
    limit = DAILY_LIMITS.get(provider)
    if limit is None:
        return True

    today = datetime.now(timezone.utc).date()
    row = await fetchrow(
        "SELECT count FROM budget WHERE provider = $1 AND date = $2",
        provider,
        today,
    )
    current = row["count"] if row else 0
    return current < limit


async def increment_budget(provider: str) -> int:
    """Increment today's usage counter. Returns new count.

    NOTE: This does NOT enforce DAILY_LIMITS. Use use_budget() for atomic
    check-and-consume. This function is for unconditional tracking only.
    """
    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)

    row = await fetchrow(
        """
        INSERT INTO budget (provider, date, count, created_at)
        VALUES ($1, $2, 1, $3)
        ON CONFLICT (provider, date) DO UPDATE SET count = budget.count + 1
        RETURNING count
        """,
        provider,
        today,
        now,
    )
    if row is None:
        raise RuntimeError(f"budget increment for {provider} returned no row")
    return row["count"]


async def use_budget(provider: str) -> bool:
    """Atomically consume one unit of budget if available. Returns True if consumed."""
    limit = DAILY_LIMITS.get(provider)
    if limit is None:
        return True
    if limit <= 0:
        return False

    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)

    row = await fetchrow(
        """
        INSERT INTO budget (provider, date, count, created_at)
        VALUES ($1, $2, 1, $3)
        ON CONFLICT (provider, date) DO UPDATE
            SET count = budget.count + 1
            WHERE budget.count < $4
        RETURNING count
        """,
        provider,
        today,
        now,
        limit,
    )
    return row is not None


async def get_budget_status() -> dict[str, dict]:
    """Return current budget status for all tracked providers."""
    from src.db import fetch

    today = datetime.now(timezone.utc).date()

    # Single query for all providers instead of N sequential roundtrips
    rows = await fetch(
        "SELECT provider, count FROM budget WHERE date = $1",
        today,
    )
    counts = {row["provider"]: row["count"] for row in rows}

    status = {}
    for provider, limit in DAILY_LIMITS.items():
        used = counts.get(provider, 0)
        status[provider] = {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "exhausted": used >= limit,
        }

    return status
