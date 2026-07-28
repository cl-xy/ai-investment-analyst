"""
Cache manager. PostgreSQL-backed stale-while-revalidate.

Per-source TTLs, background refresh, and provider budget guards.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any, Awaitable, Callable

from src.db import execute, fetchrow
from src.logging_config import get_logger

_log = get_logger("cache.refresh")

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


def _normalize(data: Any) -> Any:
    """Normalize cached data to canonical Python types.

    Tool results may arrive as JSON strings (from direct_tools._wrap_sync).
    PostgreSQL JSONB stores them as quoted strings, and asyncpg returns them
    as Python str. This function ensures callers always get dict/list/scalar,
    never a JSON-encoded string masquerading as data.
    """
    if isinstance(data, str):
        try:
            return json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return data
    return data


class CacheManager:
    """PostgreSQL stale-while-revalidate cache layer."""

    def __init__(self):
        self._refresh_tasks: set[asyncio.Task] = set()
        self._pending_refreshes: dict[str, asyncio.Task] = {}  # key -> task (dedup)

    def _task_cleanup(self, task: asyncio.Task, *, key: str) -> None:
        """Done-callback for background refresh tasks. Captures only key, not full scope."""
        self._refresh_tasks.discard(task)
        self._pending_refreshes.pop(key, None)

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
        Never caches error responses.
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
                data = _normalize(row["data"])
                # Invalidate cached error responses so they get re-fetched
                if isinstance(data, dict) and "error" in data and len(data) <= 2:
                    _log.info("cache_invalidate_error key=%s", key)
                # Invalidate empty responses (from previous silent failures)
                elif data in ({}, [], "", None):
                    _log.info("cache_invalidate_empty key=%s", key)
                else:
                    stale_at = row["stale_at"]
                    source_id = row["source_id"]

                    if now < stale_at:
                        return data, source_id, True

                    # Stale: serve immediately, refresh in background (deduplicated)
                    if key not in self._pending_refreshes:
                        task = asyncio.create_task(
                            self._refresh(key, provider, tool, ticker, fetch_fn, ttl)
                        )
                        self._pending_refreshes[key] = task
                        self._refresh_tasks.add(task)
                        task.add_done_callback(partial(self._task_cleanup, key=key))
                    return data, source_id, True

        # Cache miss, fetch fresh
        data = _normalize(await fetch_fn())
        # Never cache error responses
        if isinstance(data, dict) and "error" in data and len(data) <= 2:
            raise RuntimeError(f"Tool returned error: {data.get('error')}")
        # Never cache empty responses (transient failures that returned no data)
        if data in ({}, [], "", None):
            raise RuntimeError(f"Tool returned empty data for {key}")
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
        """Background refresh for stale-while-revalidate. Respects provider budget."""
        try:
            # Check budget before making the API call to avoid untracked spend
            from src.cache.budget import check_budget

            if not await check_budget(provider):
                _log.info("background_refresh_skipped_budget key=%s provider=%s", key, provider)
                return

            data = _normalize(await fetch_fn())
            # Never cache error responses in background refresh either
            if isinstance(data, dict) and "error" in data and len(data) <= 2:
                _log.warning("background_refresh_got_error key=%s error=%s", key, data.get("error"))
                return
            # Never cache empty responses in background refresh
            if data in ({}, [], "", None):
                _log.warning("background_refresh_got_empty key=%s", key)
                return
            source_id = f"{provider}:{ticker}:{int(time.time())}"
            await self._store(key, data, source_id, provider, ttl, datetime.now(timezone.utc))
        except Exception as exc:
            _log.warning(
                "background_refresh_failed key=%s provider=%s error=%s",
                key,
                provider,
                exc,
            )

    async def _store(
        self,
        key: str,
        data: Any,
        source_id: str,
        provider: str,
        ttl: dict[str, int],
        now: datetime,
    ):
        """Upsert a cache entry. Normalizes data before storing to prevent double-encoding."""
        data = _normalize(data)
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
            key,
            json.dumps(data),
            source_id,
            provider,
            now,
            stale_at,
            expires_at,
        )

    async def get_cached_only(self, provider: str, tool: str, ticker: str) -> tuple[Any, str, bool]:
        """
        Return cached data without fetching. Used when budget is exhausted.
        Returns (data, source_id, True) if cached, (None, "", False) if no cache.
        """
        key = f"{provider}:{tool}:{ticker}"
        row = await fetchrow("SELECT data, source_id FROM cache WHERE key = $1", key)
        if row is not None:
            return _normalize(row["data"]), row["source_id"], True
        return None, "", False


# Singleton
cache_manager = CacheManager()
