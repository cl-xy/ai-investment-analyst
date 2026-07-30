"""
Tests for the cache manager and budget tracking.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.cache.manager import CacheManager, _get_ttl


class TestTTLConfig:
    def test_known_provider_tool(self):
        ttl = _get_ttl("yfinance", "get_quote")
        assert ttl["fresh"] == 900
        assert ttl["stale"] == 3600
        assert ttl["expire"] == 14400

    def test_sec_edgar_permanent(self):
        ttl = _get_ttl("sec_edgar", "get_latest_filing_summary")
        assert ttl["expire"] == 0

    def test_unknown_provider_uses_default(self):
        ttl = _get_ttl("unknown_provider", "unknown_tool")
        assert ttl["fresh"] == 3600
        assert ttl["stale"] == 7200
        assert ttl["expire"] == 86400


class TestCacheManager:
    @pytest.mark.asyncio
    @patch("src.cache.manager.fetchrow")
    @patch("src.cache.manager.execute")
    async def test_cache_miss_calls_fetch(self, mock_execute, mock_fetchrow):
        mock_fetchrow.return_value = None
        mock_execute.return_value = "INSERT 0 1"

        cache = CacheManager()
        fetch_fn = AsyncMock(return_value={"price": 875.0})

        data, source_id, cached = await cache.get_or_fetch(
            "yfinance", "get_quote", "NVDA", fetch_fn
        )

        assert data == {"price": 875.0}
        assert cached is False
        assert "yfinance:get_quote:NVDA:" in source_id
        fetch_fn.assert_called_once()
        mock_execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.cache.manager.fetchrow")
    async def test_cache_fresh_hit(self, mock_fetchrow):
        now = datetime.now(timezone.utc)
        mock_fetchrow.return_value = {
            "key": "yfinance:get_quote:NVDA",
            "data": {"price": 870.0},
            "source_id": "yfinance:NVDA:1706140000",
            "stale_at": now + timedelta(minutes=10),
            "expires_at": now + timedelta(hours=4),
        }

        cache = CacheManager()
        fetch_fn = AsyncMock()

        data, source_id, cached = await cache.get_or_fetch(
            "yfinance", "get_quote", "NVDA", fetch_fn
        )

        assert data == {"price": 870.0}
        assert cached is True
        fetch_fn.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.cache.manager.execute")
    @patch("src.cache.manager.fetchrow")
    async def test_cache_stale_serves_and_refreshes(self, mock_fetchrow, mock_execute):
        now = datetime.now(timezone.utc)
        mock_fetchrow.return_value = {
            "key": "yfinance:get_quote:NVDA",
            "data": {"price": 860.0},
            "source_id": "yfinance:NVDA:1706130000",
            "stale_at": now - timedelta(minutes=5),
            "expires_at": now + timedelta(hours=2),
        }
        mock_execute.return_value = "INSERT 0 1"

        cache = CacheManager()
        fetch_fn = AsyncMock(return_value={"price": 880.0})

        data, source_id, cached = await cache.get_or_fetch(
            "yfinance", "get_quote", "NVDA", fetch_fn
        )

        # Should return stale data immediately
        assert data == {"price": 860.0}
        assert cached is True

        # Give background task a chance to run
        await asyncio.sleep(0.05)
        fetch_fn.assert_called_once()
