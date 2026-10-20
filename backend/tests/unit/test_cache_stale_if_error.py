"""Stale-if-error: serve the last good value, labelled, when a refresh fails."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.cache.manager import CacheManager


def _row(age: timedelta, *, expired: bool, data=None):
    now = datetime.now(timezone.utc)
    return {
        "data": data if data is not None else {"revenue": 1000},
        "source_id": "yfinance:get_fundamentals:NVDA:1",
        "fetched_at": now - age,
        "stale_at": now - age + timedelta(days=1),
        "expires_at": now - timedelta(seconds=1) if expired else now + timedelta(days=1),
    }


@pytest.mark.asyncio
async def test_expired_entry_is_served_when_refresh_fails():
    row = _row(timedelta(days=10), expired=True)
    cache = CacheManager()
    fetch_fn = AsyncMock(side_effect=RuntimeError("Tool get_fundamentals failed: 429"))

    with patch("src.cache.manager.fetchrow", AsyncMock(return_value=row)):
        data, source_id, meta = await cache.get_or_fetch_with_meta(
            "yfinance", "get_fundamentals", "NVDA", fetch_fn
        )

    assert data == {"revenue": 1000}
    assert source_id == row["source_id"]
    assert meta.cached and meta.stale_on_error
    assert 10 * 86400 - 5 <= meta.age_seconds <= 10 * 86400 + 5


@pytest.mark.asyncio
async def test_value_older_than_the_limit_is_not_served():
    # Fundamentals expire at 7d and may be served up to 30d beyond that.
    row = _row(timedelta(days=60), expired=True)
    cache = CacheManager()
    fetch_fn = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("src.cache.manager.fetchrow", AsyncMock(return_value=row)):
        with pytest.raises(RuntimeError):
            await cache.get_or_fetch_with_meta("yfinance", "get_fundamentals", "NVDA", fetch_fn)


@pytest.mark.asyncio
async def test_tools_without_a_stale_allowance_still_raise():
    row = _row(timedelta(days=1), expired=True)
    cache = CacheManager()
    fetch_fn = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("src.cache.manager.fetchrow", AsyncMock(return_value=row)):
        with pytest.raises(RuntimeError):
            await cache.get_or_fetch_with_meta(
                "stocktwits", "get_ticker_sentiment", "NVDA", fetch_fn
            )


@pytest.mark.asyncio
async def test_cached_error_payload_is_never_served_as_stale():
    row = _row(timedelta(days=10), expired=True, data={"error": "old failure"})
    cache = CacheManager()
    fetch_fn = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("src.cache.manager.fetchrow", AsyncMock(return_value=row)):
        with pytest.raises(RuntimeError):
            await cache.get_or_fetch_with_meta("yfinance", "get_fundamentals", "NVDA", fetch_fn)


@pytest.mark.asyncio
async def test_successful_refresh_is_not_marked_stale():
    cache = CacheManager()
    fetch_fn = AsyncMock(return_value={"revenue": 2000})

    with (
        patch("src.cache.manager.fetchrow", AsyncMock(return_value=None)),
        patch("src.cache.manager.execute", AsyncMock(return_value="INSERT 0 1")),
    ):
        data, _sid, meta = await cache.get_or_fetch_with_meta(
            "yfinance", "get_fundamentals", "NVDA", fetch_fn
        )

    assert data == {"revenue": 2000}
    assert not meta.cached and not meta.stale_on_error
