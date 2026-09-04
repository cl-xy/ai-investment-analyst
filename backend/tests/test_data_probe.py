"""
Tests for the lightweight alert data probe.
"""

import asyncio
from unittest.mock import patch

import pytest

from src.alerts.data_probe import (
    _bullish_ratio_to_sentiment,
    _probe_cache,
    probe_ticker,
    probe_tickers,
)


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    _probe_cache.clear()
    yield
    _probe_cache.clear()


class TestBullishRatioConversion:
    def test_neutral_ratio_maps_to_zero(self):
        assert _bullish_ratio_to_sentiment(0.5) == 0.0

    def test_fully_bullish_maps_to_one(self):
        assert _bullish_ratio_to_sentiment(1.0) == 1.0

    def test_fully_bearish_maps_to_negative_one(self):
        assert _bullish_ratio_to_sentiment(0.0) == -1.0

    def test_none_passthrough(self):
        assert _bullish_ratio_to_sentiment(None) is None


class TestProbeTicker:
    @pytest.mark.asyncio
    async def test_probe_aggregates_all_sources(self):
        with (
            patch("src.alerts.data_probe.yf_client.get_quote", return_value={"price": 123.45}),
            patch(
                "src.alerts.data_probe.stocktwits.get_ticker_sentiment",
                return_value={"bullish_ratio": 0.75},
            ),
            patch(
                "src.alerts.data_probe.search_filings",
                return_value=[{"filed_date": "2026-08-20", "form_type": "8-K"}],
            ),
            patch(
                "src.alerts.data_probe._fetch_ticker_news",
                return_value=[{"title": "a"}, {"title": "b"}],
            ),
        ):
            result = await probe_ticker("NVDA")

        assert result.ticker == "NVDA"
        assert result.current_price == 123.45
        assert result.sentiment_score == 0.5
        assert result.latest_filing_date == "2026-08-20"
        assert result.latest_filing_form_type == "8-K"
        assert result.article_count == 2
        assert result.data_gaps == []

    @pytest.mark.asyncio
    async def test_probe_degrades_gracefully_on_source_failure(self):
        with (
            patch("src.alerts.data_probe.yf_client.get_quote", side_effect=RuntimeError("boom")),
            patch(
                "src.alerts.data_probe.stocktwits.get_ticker_sentiment",
                return_value={},
            ),
            patch("src.alerts.data_probe.search_filings", return_value=[]),
            patch("src.alerts.data_probe._fetch_ticker_news", return_value=[]),
        ):
            result = await probe_ticker("BADCO")

        assert result.current_price is None
        assert result.sentiment_score is None
        assert result.latest_filing_date is None
        assert result.article_count == 0
        assert "probe_price_fetch_failed" in result.data_gaps
        assert "probe_sentiment_unavailable" in result.data_gaps
        assert "probe_no_recent_filings" in result.data_gaps

    @pytest.mark.asyncio
    async def test_probe_uses_cache_on_second_call(self):
        call_count = 0

        def _get_quote(_ticker):
            nonlocal call_count
            call_count += 1
            return {"price": 10.0}

        with (
            patch("src.alerts.data_probe.yf_client.get_quote", side_effect=_get_quote),
            patch("src.alerts.data_probe.stocktwits.get_ticker_sentiment", return_value={}),
            patch("src.alerts.data_probe.search_filings", return_value=[]),
            patch("src.alerts.data_probe._fetch_ticker_news", return_value=[]),
        ):
            first = await probe_ticker("AAPL")
            second = await probe_ticker("AAPL")

        assert call_count == 1
        assert first is second

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self):
        call_count = 0

        def _get_quote(_ticker):
            nonlocal call_count
            call_count += 1
            return {"price": 10.0 + call_count}

        with (
            patch("src.alerts.data_probe.yf_client.get_quote", side_effect=_get_quote),
            patch("src.alerts.data_probe.stocktwits.get_ticker_sentiment", return_value={}),
            patch("src.alerts.data_probe.search_filings", return_value=[]),
            patch("src.alerts.data_probe._fetch_ticker_news", return_value=[]),
        ):
            first = await probe_ticker("MSFT")
            second = await probe_ticker("MSFT", force_refresh=True)

        assert call_count == 2
        assert first.current_price != second.current_price

    @pytest.mark.asyncio
    async def test_probe_normalizes_ticker_case(self):
        with (
            patch("src.alerts.data_probe.yf_client.get_quote", return_value={"price": 1.0}),
            patch("src.alerts.data_probe.stocktwits.get_ticker_sentiment", return_value={}),
            patch("src.alerts.data_probe.search_filings", return_value=[]),
            patch("src.alerts.data_probe._fetch_ticker_news", return_value=[]),
        ):
            result = await probe_ticker("  nvda  ")
        assert result.ticker == "NVDA"


class TestProbeTimeoutCompliance:
    @pytest.mark.asyncio
    async def test_slow_source_times_out_without_hanging(self):
        """A hanging source should time out per-source (bounded by
        _PROBE_TIMEOUT) rather than blocking the probe indefinitely."""

        async def _slow(*_args, **_kwargs):
            await asyncio.sleep(30)
            return {"price": 1.0}

        with (
            patch("src.alerts.data_probe.asyncio.to_thread", side_effect=_slow),
            patch("src.alerts.data_probe._PROBE_TIMEOUT", 0.2),
        ):
            result = await asyncio.wait_for(probe_ticker("SLOW"), timeout=10)

        # All sub-fetches should have failed/timed out but the probe itself
        # returns promptly rather than hanging for 30s.
        assert result.current_price is None


class TestProbeTickers:
    @pytest.mark.asyncio
    async def test_probe_multiple_tickers_bounded_concurrency(self):
        with (
            patch("src.alerts.data_probe.yf_client.get_quote", return_value={"price": 1.0}),
            patch("src.alerts.data_probe.stocktwits.get_ticker_sentiment", return_value={}),
            patch("src.alerts.data_probe.search_filings", return_value=[]),
            patch("src.alerts.data_probe._fetch_ticker_news", return_value=[]),
        ):
            results = await probe_tickers(["AAPL", "MSFT", "GOOGL"], concurrency=2)

        assert set(results.keys()) == {"AAPL", "MSFT", "GOOGL"}

    @pytest.mark.asyncio
    async def test_probe_multiple_tickers_isolates_failures(self):
        async def _bounded_probe(ticker, *, force_refresh=False):
            if ticker == "BAD":
                raise RuntimeError("simulated failure")
            import time

            from src.alerts.data_probe import ProbeResult

            return ProbeResult(
                ticker=ticker,
                current_price=1.0,
                sentiment_score=None,
                latest_filing_date=None,
                latest_filing_form_type=None,
                article_count=0,
                fetched_at=time.monotonic(),
                data_gaps=[],
            )

        with patch("src.alerts.data_probe.probe_ticker", side_effect=_bounded_probe):
            results = await probe_tickers(["GOOD", "BAD"], concurrency=2)

        assert "GOOD" in results
        assert "BAD" not in results
