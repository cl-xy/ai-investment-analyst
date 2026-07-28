"""
Provider daily budget tracking. PostgreSQL-backed.

Prevents exceeding free-tier rate limits on external APIs.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from src.db import fetchrow

# Conservative daily limits (leave headroom for manual use)
DAILY_LIMITS: dict[str, int] = {
    "alpha_vantage": 20,
    "newsapi": 90,
    "groq": 1400,
}


async def check_budget(provider: str) -> bool:
    """Return True if the provider has remaining budget for today."""
    limit = DAILY_LIMITS.get(provider)
    if limit is None:
        return True

    today = date.today()
    row = await fetchrow(
        "SELECT count FROM budget WHERE provider = $1 AND date = $2",
        provider,
        today,
    )
    current = row["count"] if row else 0
    return current < limit


async def increment_budget(provider: str) -> int:
    """Increment today's usage counter. Returns new count."""
    today = date.today()
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
    return row["count"]


async def use_budget(provider: str) -> bool:
    """Atomically consume one unit of budget if available. Returns True if consumed."""
    limit = DAILY_LIMITS.get(provider)
    if limit is None:
        return True

    today = date.today()
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
    today = date.today()
    status = {}

    for provider, limit in DAILY_LIMITS.items():
        row = await fetchrow(
            "SELECT count FROM budget WHERE provider = $1 AND date = $2",
            provider,
            today,
        )
        used = row["count"] if row else 0
        status[provider] = {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "exhausted": used >= limit,
        }

    return status
