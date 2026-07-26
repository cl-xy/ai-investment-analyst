"""
Provider daily budget tracking.

Prevents exceeding free-tier rate limits on external APIs.
Uses MongoDB for persistence (survives restarts).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from src.api.db import get_collection


# Conservative daily limits (leave headroom for manual use)
DAILY_LIMITS: dict[str, int] = {
    "alpha_vantage": 20,   # API allows 25/day, save 5
    "newsapi": 90,         # API allows 100/day, save 10
    "groq": 1400,          # Conservative of 14400 req/day
}


async def check_budget(provider: str) -> bool:
    """Return True if the provider has remaining budget for today."""
    limit = DAILY_LIMITS.get(provider)
    if limit is None:
        return True  # No limit configured

    collection = get_collection("budget")
    today = date.today().isoformat()
    doc = await collection.find_one({"provider": provider, "date": today})
    current = doc["count"] if doc else 0
    return current < limit


async def increment_budget(provider: str) -> int:
    """Increment today's usage counter. Returns new count."""
    collection = get_collection("budget")
    today = date.today().isoformat()

    result = await collection.find_one_and_update(
        {"provider": provider, "date": today},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
        return_document=True,
    )
    return result["count"]


async def get_budget_status() -> dict[str, dict]:
    """Return current budget status for all tracked providers."""
    collection = get_collection("budget")
    today = date.today().isoformat()

    status = {}
    for provider, limit in DAILY_LIMITS.items():
        doc = await collection.find_one({"provider": provider, "date": today})
        used = doc["count"] if doc else 0
        status[provider] = {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "exhausted": used >= limit,
        }
    return status
