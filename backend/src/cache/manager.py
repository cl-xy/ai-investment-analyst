"""
Cache manager. PostgreSQL-backed stale-while-revalidate.

Per-source TTLs, background refresh, and provider budget guards.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from src.api.db import fetchrow, execute


# TTL configuration per provider/tool combination
TTL_CONFIG: dict[str, dict[str, int]] = {
    "yfinance:get_quote": {"fresh": 900, "stale": 3600, "expire": 14400},
    "yfinance:get_fundamentals": {"fresh": 86400, "stale": 172800, "expire": 604800},
    "yfinance:get_technical_indicators": {"fresh": 900, "stale": 3600, "expire": 14400},
    "newsapi:get_ticker_news": {"fresh": 21600, "stale": 43200, "expire": 86400},
    "sec_edgar:get_latest_filing_summary": {"fresh": 604800, "stale": 2592000, "expire": 0},
    "alpha_vantage:default": {"fresh": 86400, "stale": 172800, "expire": 604800},
}

DEFAULT_TTL = {"fresh": 3600, "stale": 7200, "expire": 86400}


def _get_ttl(provider: str, tool: str) -> dict[str, int]:
    key = f"{provider}:{tool}"
    return TTL_CONFIG.get(key, TTL_CONFIG.get(f"{provider}:default", DEFAULT_TTL))


class CacheManager:
    """PostgreSQL stale-while-revalidate cache layer."""

    def __init__(self):
        self._refresh_tasks: set[asyncio.Task] = set()

    async def get(self, key: str) -> dict | None:
        """Get a cache entry by key. Returns None if not found or expired."""
        row = await fetchrow("SELECT * FROM cache WHERE key = $1", key)
        if row is None:
            return None

        if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
            return None

        return dict(row)

    async def get_or_fetch(
        self,
        provider: str,
        tool: str,
        ticker: str,
        fetch_fn: Callable[[], Awaitable[Any]],
    ) -> tuple[Any, str, bool]:
        """
        Get cached data or fetch fresh. Returns (data, source_id, was_cached).
        """
        key = f"{provider}:{tool}:{ticker}"
        ttl = _get_ttl(provider, tool)
        now = datetime.now(timezone.utc)

        row = await fetchrow("SELECT * FROM cache WHERE key = $1", key)

        if row is not None:
            expires_at = row["expires_at"]
            if expires_at and expires_at < now:
                # Hard expired, treat as miss
                pass
            else:
                stale_at = row["stale_at"]
                source_id = row["source_id"]
                data = row["data"]

                if now < stale_at:
                    return data, source_id, True

                # Stale: serve immediately, refresh in background
                task = asyncio.create_task(
                    self._refresh(key, provider, tool, ticker, fetch_fn, ttl)
                )
                self._refresh_tasks.add(task)
                task.add_done_callback(self._refresh_tasks.discard)
                return data, source_id, True

        # Cache miss, fetch fresh
        data = await fetch_fn()
        source_id = f"{provider}:{ticker}:{int(time.time())}"
        await self._store(key, data, source_id, provider, ttl, now)
        return data, source_id, False

    async def _refresh(
        self, key: str, provider: str, tool: str, ticker: str,
        fetch_fn: Callable[[], Awaitable[Any]], ttl: dict[str, int],
    ):
        """Background refresh for stale-while-revalidate."""
        try:
            data = await fetch_fn()
            source_id = f"{provider}:{ticker}:{int(time.time())}"
            await self._store(key, data, source_id, provider, ttl, datetime.now(timezone.utc))
        except Exception:
            pass

    async def _store(
        self, key: str, data: Any, source_id: str,
        provider: str, ttl: dict[str, int], now: datetime,
    ):
        """Upsert a cache entry."""
        stale_at = now + timedelta(seconds=ttl["fresh"])
        expires_at = now + timedelta(seconds=ttl["expire"]) if ttl["expire"] > 0 else None

        await execute(
            """
            INSERT INTO cache (key, data, source_id, provider, fetched_at, stale_at, expires_at)
            VALUES ($1, $2::jsonb, $3, $4, $5, $6, $7)
            ON CONFLICT (key) DO UPDATE SET
                data = EXCLUDED.data,
                source_id = EXCLUDED.source_id,
                provider = EXCLUDED.provider,
                fetched_at = EXCLUDED.fetched_at,
                stale_at = EXCLUDED.stale_at,
                expires_at = EXCLUDED.expires_at
            """,
            key, json.dumps(data), source_id, provider, now, stale_at, expires_at,
        )


    async def get_cached_only(self, provider: str, tool: str, ticker: str) -> tuple[Any, str, bool]:
        """
        Return cached data without fetching. Used when budget is exhausted.
        Returns (data, source_id, True) if cached, (None, "", False) if no cache.
        """
        key = f"{provider}:{tool}:{ticker}"
        row = await fetchrow("SELECT data, source_id FROM cache WHERE key = $1", key)
        if row is not None:
            return row["data"], row["source_id"], True
        return None, "", False


# Singleton
cache_manager = CacheManager()
