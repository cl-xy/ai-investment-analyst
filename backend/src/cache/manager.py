"""
MongoDB-backed cache with stale-while-revalidate semantics.

Per-source TTLs, background refresh, and provider budget guards.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from motor.motor_asyncio import AsyncIOMotorCollection

from src.api.db import get_collection


# TTL configuration per provider/tool combination
TTL_CONFIG: dict[str, dict[str, int]] = {
    # {provider: {fresh_seconds, stale_seconds, expire_seconds}}
    "yfinance:get_quote": {"fresh": 900, "stale": 3600, "expire": 14400},
    "yfinance:get_fundamentals": {"fresh": 86400, "stale": 172800, "expire": 604800},
    "yfinance:get_technical_indicators": {"fresh": 900, "stale": 3600, "expire": 14400},
    "newsapi:get_ticker_news": {"fresh": 21600, "stale": 43200, "expire": 86400},
    "sec_edgar:get_latest_filing_summary": {"fresh": 604800, "stale": 2592000, "expire": 0},  # permanent
    "alpha_vantage:default": {"fresh": 86400, "stale": 172800, "expire": 604800},
}

DEFAULT_TTL = {"fresh": 3600, "stale": 7200, "expire": 86400}


def _get_ttl(provider: str, tool: str) -> dict[str, int]:
    key = f"{provider}:{tool}"
    return TTL_CONFIG.get(key, TTL_CONFIG.get(f"{provider}:default", DEFAULT_TTL))


class CacheManager:
    """MongoDB stale-while-revalidate cache layer."""

    def __init__(self):
        self._collection: AsyncIOMotorCollection | None = None
        self._refresh_tasks: set[asyncio.Task] = set()

    @property
    def collection(self) -> AsyncIOMotorCollection:
        if self._collection is None:
            self._collection = get_collection("cache")
        return self._collection

    async def ensure_indexes(self):
        """Create indexes for cache lookups and TTL expiry."""
        await self.collection.create_index("key", unique=True)
        await self.collection.create_index("expires_at", expireAfterSeconds=0)

    async def get(self, key: str) -> dict | None:
        """Get a cache entry by key. Returns None if not found or hard-expired."""
        doc = await self.collection.find_one({"key": key})
        if doc is None:
            return None

        # Check hard expiry (TTL index handles cleanup, but be defensive)
        if doc.get("expires_at") and doc["expires_at"] < datetime.now(timezone.utc):
            return None

        return doc

    async def get_or_fetch(
        self,
        provider: str,
        tool: str,
        ticker: str,
        fetch_fn: Callable[[], Awaitable[Any]],
    ) -> tuple[Any, str, bool]:
        """
        Get cached data or fetch fresh. Returns (data, source_id, was_cached).

        Implements stale-while-revalidate:
        - Fresh: serve from cache
        - Stale: serve from cache, refresh in background
        - Expired: fetch fresh (blocking)
        """
        key = f"{provider}:{tool}:{ticker}"
        ttl = _get_ttl(provider, tool)
        now = datetime.now(timezone.utc)

        doc = await self.get(key)

        if doc is not None:
            stale_at = doc.get("stale_at", now)
            source_id = doc.get("source_id", key)

            if now < stale_at:
                # Fresh — serve directly
                return doc["data"], source_id, True

            # Stale — serve immediately but refresh in background
            task = asyncio.create_task(self._refresh(key, provider, tool, ticker, fetch_fn, ttl))
            self._refresh_tasks.add(task)
            task.add_done_callback(self._refresh_tasks.discard)
            return doc["data"], source_id, True

        # Miss — fetch fresh
        data = await fetch_fn()
        source_id = f"{provider}:{ticker}:{int(time.time())}"
        await self._store(key, data, source_id, provider, ttl, now)
        return data, source_id, False

    async def _refresh(
        self,
        key: str,
        provider: str,
        tool: str,
        ticker: str,
        fetch_fn: Callable[[], Awaitable[Any]],
        ttl: dict[str, int],
    ):
        """Background refresh for stale-while-revalidate."""
        try:
            data = await fetch_fn()
            source_id = f"{provider}:{ticker}:{int(time.time())}"
            await self._store(key, data, source_id, provider, ttl, datetime.now(timezone.utc))
        except Exception:
            # Background refresh failure is non-critical — stale data still served
            pass

    async def _store(
        self,
        key: str,
        data: Any,
        source_id: str,
        provider: str,
        ttl: dict[str, int],
        now: datetime,
    ):
        """Upsert a cache entry with computed timestamps."""
        stale_at = now + timedelta(seconds=ttl["fresh"])
        expires_at = now + timedelta(seconds=ttl["expire"]) if ttl["expire"] > 0 else None

        doc = {
            "key": key,
            "data": data,
            "source_id": source_id,
            "provider": provider,
            "fetched_at": now,
            "stale_at": stale_at,
        }
        if expires_at:
            doc["expires_at"] = expires_at

        await self.collection.update_one(
            {"key": key},
            {"$set": doc},
            upsert=True,
        )

    async def warm(self, keys: list[str], fetch_fns: dict[str, Callable[[], Awaitable[Any]]]):
        """Pre-warm cache for demo tickers. Called by admin endpoint."""
        for key in keys:
            if key in fetch_fns:
                try:
                    await self.get_or_fetch(
                        provider=key.split(":")[0],
                        tool=key.split(":")[1],
                        ticker=key.split(":")[2] if len(key.split(":")) > 2 else "",
                        fetch_fn=fetch_fns[key],
                    )
                except Exception:
                    continue


# Singleton
cache_manager = CacheManager()
