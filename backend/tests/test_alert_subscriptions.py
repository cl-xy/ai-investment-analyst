"""
Tests for watchlist-based alert subscriptions (backend/src/alerts/subscriptions.py).
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.alerts.subscriptions import (
    DEFAULT_TRIGGER_TYPES,
    get_active_subscription_tickers,
    list_subscriptions,
    subscribe_ticker,
    unsubscribe_ticker,
)


class TestSubscribeTicker:
    @pytest.mark.asyncio
    async def test_subscribe_normalizes_ticker_case(self):
        fake_row = {
            "ticker": "NVDA",
            "source": "watchlist",
            "trigger_types": '["sec", "sentiment", "peer", "price"]',
            "active": True,
        }
        with patch("src.alerts.subscriptions.fetchrow", new=AsyncMock(return_value=fake_row)):
            sub = await subscribe_ticker("  nvda  ")
        assert sub.ticker == "NVDA"

    @pytest.mark.asyncio
    async def test_subscribe_uses_default_trigger_types(self):
        captured = {}

        async def _fake_fetchrow(query, *args):
            captured["args"] = args
            return {
                "ticker": "AAPL",
                "source": "watchlist",
                "trigger_types": args[2],
                "active": True,
            }

        with patch("src.alerts.subscriptions.fetchrow", side_effect=_fake_fetchrow):
            sub = await subscribe_ticker("AAPL")

        assert sub.trigger_types == DEFAULT_TRIGGER_TYPES

    @pytest.mark.asyncio
    async def test_subscribe_custom_trigger_types(self):
        async def _fake_fetchrow(query, *args):
            return {"ticker": "TSLA", "source": "watchlist", "trigger_types": args[2], "active": True}

        with patch("src.alerts.subscriptions.fetchrow", side_effect=_fake_fetchrow):
            sub = await subscribe_ticker("TSLA", trigger_types=["price"])
        assert sub.trigger_types == ["price"]

    @pytest.mark.asyncio
    async def test_subscribe_falls_back_to_refetch_on_no_conflict_row(self):
        call_count = 0

        async def _fake_fetchrow(query, *args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None
            return {"ticker": "MSFT", "source": "watchlist", "trigger_types": "[]", "active": True}

        with patch("src.alerts.subscriptions.fetchrow", side_effect=_fake_fetchrow):
            sub = await subscribe_ticker("MSFT")

        assert sub.ticker == "MSFT"
        assert call_count == 2


class TestUnsubscribeTicker:
    @pytest.mark.asyncio
    async def test_unsubscribe_returns_true_when_row_updated(self):
        with patch("src.alerts.subscriptions.execute", new=AsyncMock(return_value="UPDATE 1")):
            result = await unsubscribe_ticker("NVDA")
        assert result is True

    @pytest.mark.asyncio
    async def test_unsubscribe_returns_false_when_no_row_updated(self):
        with patch("src.alerts.subscriptions.execute", new=AsyncMock(return_value="UPDATE 0")):
            result = await unsubscribe_ticker("NVDA")
        assert result is False


class TestListSubscriptions:
    @pytest.mark.asyncio
    async def test_list_returns_active_subscriptions(self):
        fake_rows = [
            {"ticker": "AAPL", "source": "watchlist", "trigger_types": '["price"]', "active": True},
            {"ticker": "NVDA", "source": "portfolio", "trigger_types": "[]", "active": True},
        ]
        with patch("src.alerts.subscriptions.fetch", new=AsyncMock(return_value=fake_rows)):
            subs = await list_subscriptions()
        assert [s.ticker for s in subs] == ["AAPL", "NVDA"]
        assert subs[0].trigger_types == ["price"]

    @pytest.mark.asyncio
    async def test_get_active_subscription_tickers(self):
        fake_rows = [{"ticker": "AAPL"}, {"ticker": "NVDA"}]
        with patch("src.alerts.subscriptions.fetch", new=AsyncMock(return_value=fake_rows)):
            tickers = await get_active_subscription_tickers()
        assert tickers == ["AAPL", "NVDA"]
