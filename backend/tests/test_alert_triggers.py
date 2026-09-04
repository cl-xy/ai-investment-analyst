"""
Tests for event trigger monitors.
"""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.alerts.data_probe import ProbeResult
from src.alerts.last_analysis import LastAnalysisSnapshot
from src.alerts.triggers.peer_trigger import check_peer_signal_trigger
from src.alerts.triggers.price_trigger import check_price_trigger
from src.alerts.triggers.sec_trigger import check_sec_filing_trigger
from src.alerts.triggers.sentiment_trigger import check_sentiment_trigger
from src.alerts.triggers.trigger_manager import check_all_triggers, check_all_triggers_for_ticker


def _snapshot(**overrides) -> LastAnalysisSnapshot:
    defaults = dict(
        ticker="NVDA",
        signal="buy",
        confidence="high",
        sentiment_score=0.5,
        risk_flags=[],
        price_data={"currentPrice": 100.0},
        fundamentals={"sector": "Technology"},
        analysis_id="test-id",
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return LastAnalysisSnapshot(**defaults)


def _probe(**overrides) -> ProbeResult:
    defaults = dict(
        ticker="NVDA",
        current_price=100.0,
        sentiment_score=0.5,
        latest_filing_date=None,
        latest_filing_form_type=None,
        article_count=5,
        fetched_at=time.monotonic(),
        data_gaps=[],
    )
    defaults.update(overrides)
    return ProbeResult(**defaults)


class TestSecFilingTrigger:
    def test_no_snapshot_skips(self):
        assert check_sec_filing_trigger(None, _probe(latest_filing_date="2026-08-10")) is None

    def test_no_filing_data_skips(self):
        assert check_sec_filing_trigger(_snapshot(), _probe(latest_filing_date=None)) is None

    def test_filing_before_last_analysis_skips(self):
        snapshot = _snapshot(created_at=datetime(2026, 8, 15, tzinfo=timezone.utc))
        probe = _probe(latest_filing_date="2026-08-01")
        assert check_sec_filing_trigger(snapshot, probe) is None

    def test_filing_after_last_analysis_fires(self):
        snapshot = _snapshot(created_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
        probe = _probe(latest_filing_date="2026-08-15", latest_filing_form_type="8-K")
        event = check_sec_filing_trigger(snapshot, probe)
        assert event is not None
        assert event.trigger_type == "sec_filing"
        assert "8-K" in event.summary


class TestSentimentTrigger:
    def test_no_snapshot_skips(self):
        assert check_sentiment_trigger(None, _probe(sentiment_score=0.9)) is None

    def test_no_probe_sentiment_skips(self):
        assert check_sentiment_trigger(_snapshot(), _probe(sentiment_score=None)) is None

    def test_small_delta_skips(self):
        snapshot = _snapshot(sentiment_score=0.5)
        probe = _probe(sentiment_score=0.55)
        assert check_sentiment_trigger(snapshot, probe) is None

    def test_large_delta_fires(self):
        snapshot = _snapshot(sentiment_score=0.8)
        probe = _probe(sentiment_score=0.1)
        event = check_sentiment_trigger(snapshot, probe)
        assert event is not None
        assert event.trigger_type == "sentiment"
        assert "deteriorated" in event.summary

    def test_positive_swing_reports_improved(self):
        snapshot = _snapshot(sentiment_score=-0.5)
        probe = _probe(sentiment_score=0.3)
        event = check_sentiment_trigger(snapshot, probe)
        assert event is not None
        assert "improved" in event.summary


class TestPriceTrigger:
    def test_no_snapshot_skips(self):
        assert check_price_trigger(None, _probe(current_price=120.0)) is None

    def test_no_probe_price_skips(self):
        assert check_price_trigger(_snapshot(), _probe(current_price=None)) is None

    def test_small_move_skips(self):
        snapshot = _snapshot(price_data={"currentPrice": 100.0})
        probe = _probe(current_price=102.0)
        assert check_price_trigger(snapshot, probe) is None

    def test_large_move_fires(self):
        snapshot = _snapshot(price_data={"currentPrice": 100.0})
        probe = _probe(current_price=90.0)
        event = check_price_trigger(snapshot, probe)
        assert event is not None
        assert event.trigger_type == "price"
        assert "down" in event.summary

    def test_missing_price_data_in_snapshot_skips(self):
        snapshot = _snapshot(price_data={})
        probe = _probe(current_price=90.0)
        assert check_price_trigger(snapshot, probe) is None


class TestPeerSignalTrigger:
    @pytest.mark.asyncio
    async def test_no_snapshot_skips(self):
        assert await check_peer_signal_trigger(None, "NVDA") is None

    @pytest.mark.asyncio
    async def test_no_sector_skips(self):
        snapshot = _snapshot(fundamentals={})
        assert await check_peer_signal_trigger(snapshot, "NVDA") is None

    @pytest.mark.asyncio
    async def test_peer_flip_fires(self):
        snapshot = _snapshot(fundamentals={"sector": "Technology"})

        async def _fake_last_analysis(ticker):
            from src.alerts.last_analysis import LastAnalysisSnapshot as S

            return S(
                ticker=ticker,
                signal="sell",
                confidence="high",
                sentiment_score=-0.5,
                risk_flags=[],
                price_data={},
                fundamentals={},
                analysis_id="peer-id",
                created_at=datetime.now(timezone.utc),
            )

        with (
            patch(
                "src.alerts.triggers.peer_trigger.get_last_analysis",
                side_effect=_fake_last_analysis,
            ),
            patch(
                "src.alerts.triggers.peer_trigger.get_signal_as_of",
                new=AsyncMock(return_value="buy"),
            ),
        ):
            event = await check_peer_signal_trigger(snapshot, "NVDA")

        assert event is not None
        assert event.trigger_type == "peer_signal"
        assert "buy -> sell" in event.summary

    @pytest.mark.asyncio
    async def test_peer_unchanged_skips(self):
        snapshot = _snapshot(fundamentals={"sector": "Technology"})

        async def _fake_last_analysis(ticker):
            from src.alerts.last_analysis import LastAnalysisSnapshot as S

            return S(
                ticker=ticker,
                signal="buy",
                confidence="high",
                sentiment_score=0.5,
                risk_flags=[],
                price_data={},
                fundamentals={},
                analysis_id="peer-id",
                created_at=datetime.now(timezone.utc),
            )

        with (
            patch(
                "src.alerts.triggers.peer_trigger.get_last_analysis",
                side_effect=_fake_last_analysis,
            ),
            patch(
                "src.alerts.triggers.peer_trigger.get_signal_as_of",
                new=AsyncMock(return_value="buy"),
            ),
        ):
            event = await check_peer_signal_trigger(snapshot, "NVDA")

        assert event is None


class TestTriggerManagerPerTicker:
    @pytest.mark.asyncio
    async def test_aggregates_multiple_fired_triggers(self):
        snapshot = _snapshot(
            sentiment_score=0.8,
            price_data={"currentPrice": 100.0},
            created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        probe = _probe(
            sentiment_score=0.1,
            current_price=80.0,
            latest_filing_date="2026-08-10",
            latest_filing_form_type="8-K",
        )

        with patch(
            "src.alerts.triggers.trigger_manager.check_peer_signal_trigger",
            new=AsyncMock(return_value=None),
        ):
            events = await check_all_triggers_for_ticker("NVDA", snapshot, probe)

        types = {e.trigger_type for e in events}
        assert "sentiment" in types
        assert "price" in types
        assert "sec_filing" in types

    @pytest.mark.asyncio
    async def test_no_triggers_when_nothing_changed(self):
        snapshot = _snapshot()
        probe = _probe()

        with patch(
            "src.alerts.triggers.trigger_manager.check_peer_signal_trigger",
            new=AsyncMock(return_value=None),
        ):
            events = await check_all_triggers_for_ticker("NVDA", snapshot, probe)

        assert events == []

    @pytest.mark.asyncio
    async def test_peer_trigger_exception_isolated(self):
        snapshot = _snapshot()
        probe = _probe()

        with patch(
            "src.alerts.triggers.trigger_manager.check_peer_signal_trigger",
            side_effect=RuntimeError("boom"),
        ):
            events = await check_all_triggers_for_ticker("NVDA", snapshot, probe)

        # Should not raise; peer failure is isolated, other triggers unaffected
        assert isinstance(events, list)


class TestTriggerManagerAggregate:
    @pytest.mark.asyncio
    async def test_check_all_triggers_multiple_tickers(self):
        probe_results = {
            "NVDA": _probe(ticker="NVDA"),
            "AMD": _probe(ticker="AMD"),
        }

        with (
            patch(
                "src.alerts.triggers.trigger_manager.probe_tickers",
                new=AsyncMock(return_value=probe_results),
            ),
            patch(
                "src.alerts.triggers.trigger_manager.get_last_analysis",
                new=AsyncMock(return_value=None),
            ),
        ):
            results = await check_all_triggers(["NVDA", "AMD"])

        assert set(results.keys()) == {"NVDA", "AMD"}

    @pytest.mark.asyncio
    async def test_empty_ticker_list_returns_empty(self):
        results = await check_all_triggers([])
        assert results == {}

    @pytest.mark.asyncio
    async def test_missing_probe_result_skipped_gracefully(self):
        with (
            patch(
                "src.alerts.triggers.trigger_manager.probe_tickers",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "src.alerts.triggers.trigger_manager.get_last_analysis",
                new=AsyncMock(return_value=None),
            ),
        ):
            results = await check_all_triggers(["MISSING"])

        assert results["MISSING"] == []
