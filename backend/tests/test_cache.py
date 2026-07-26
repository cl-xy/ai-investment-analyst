"""
Tests for the cache manager and budget tracking.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cache.manager import CacheManager, _get_ttl


class TestTTLConfig:
    def test_known_provider_tool(self):
        ttl = _get_ttl("yfinance", "get_quote")
        assert ttl["fresh"] == 900  # 15 minutes
        assert ttl["stale"] == 3600  # 1 hour
        assert ttl["expire"] == 14400  # 4 hours

    def test_sec_edgar_permanent(self):
        ttl = _get_ttl("sec_edgar", "get_latest_filing_summary")
        assert ttl["expire"] == 0  # permanent (no expiry)

    def test_unknown_provider_uses_default(self):
        ttl = _get_ttl("unknown_provider", "unknown_tool")
        assert ttl["fresh"] == 3600
        assert ttl["stale"] == 7200
        assert ttl["expire"] == 86400


class TestCacheManager:
    @pytest.fixture
    def cache(self):
        cm = CacheManager()
        cm._collection = AsyncMock()
        return cm

    @pytest.mark.asyncio
    async def test_cache_miss_calls_fetch(self, cache):
        cache._collection.find_one = AsyncMock(return_value=None)
        cache._collection.update_one = AsyncMock()

        fetch_fn = AsyncMock(return_value={"price": 875.0})
        data, source_id, cached = await cache.get_or_fetch(
            "yfinance", "get_quote", "NVDA", fetch_fn
        )

        assert data == {"price": 875.0}
        assert cached is False
        assert "yfinance:NVDA:" in source_id
        fetch_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_fresh_hit(self, cache):
        now = datetime.now(timezone.utc)
        cache._collection.find_one = AsyncMock(return_value={
            "key": "yfinance:get_quote:NVDA",
            "data": {"price": 870.0},
            "source_id": "yfinance:NVDA:1706140000",
            "stale_at": now + timedelta(minutes=10),  # Still fresh
            "expires_at": now + timedelta(hours=4),
        })

        fetch_fn = AsyncMock()
        data, source_id, cached = await cache.get_or_fetch(
            "yfinance", "get_quote", "NVDA", fetch_fn
        )

        assert data == {"price": 870.0}
        assert cached is True
        fetch_fn.assert_not_called()  # No fetch needed

    @pytest.mark.asyncio
    async def test_cache_stale_serves_and_refreshes(self, cache):
        now = datetime.now(timezone.utc)
        cache._collection.find_one = AsyncMock(return_value={
            "key": "yfinance:get_quote:NVDA",
            "data": {"price": 860.0},
            "source_id": "yfinance:NVDA:1706130000",
            "stale_at": now - timedelta(minutes=5),  # Stale
            "expires_at": now + timedelta(hours=2),
        })
        cache._collection.update_one = AsyncMock()

        fetch_fn = AsyncMock(return_value={"price": 880.0})
        data, source_id, cached = await cache.get_or_fetch(
            "yfinance", "get_quote", "NVDA", fetch_fn
        )

        # Should return stale data immediately
        assert data == {"price": 860.0}
        assert cached is True

        # Give background task a chance to run
        await asyncio.sleep(0.05)
        # Background refresh should have been triggered
        fetch_fn.assert_called_once()
