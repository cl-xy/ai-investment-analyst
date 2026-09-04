"""
Integration tests for the alert evaluation pipeline (orchestrator).

Mocks every external boundary (DB, LLM, Telegram, data probe) so this runs
fast and deterministically while still exercising the full wiring:
triggers -> scorer -> judge -> composer -> persistence -> dispatch.
"""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.alerts.data_probe import ProbeResult
from src.alerts.drift_judge import DriftJudgment, JudgeResult
from src.alerts.last_analysis import LastAnalysisSnapshot
from src.alerts.pipeline import evaluate_all_monitored, evaluate_ticker, get_monitored_tickers
from src.alerts.triggers.events import TriggerEvent


def _snapshot(**overrides) -> LastAnalysisSnapshot:
    defaults = dict(
        ticker="NVDA",
        signal="buy",
        confidence="high",
        sentiment_score=0.8,
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
        sentiment_score=0.8,
        latest_filing_date=None,
        latest_filing_form_type=None,
        article_count=5,
        fetched_at=time.monotonic(),
        data_gaps=[],
    )
    defaults.update(overrides)
    return ProbeResult(**defaults)


class TestEvaluateTickerNoBaseline:
    @pytest.mark.asyncio
    async def test_skips_when_no_prior_analysis(self):
        with patch("src.alerts.pipeline.get_last_analysis", new=AsyncMock(return_value=None)):
            outcome = await evaluate_ticker("NEWCO")

        assert outcome.evaluated is False
        assert outcome.skip_reason == "no_prior_analysis"
        assert outcome.alert is None


class TestEvaluateTickerNoDrift:
    @pytest.mark.asyncio
    async def test_no_alert_when_drift_below_threshold(self):
        snapshot = _snapshot()
        probe = _probe()  # identical to snapshot -> zero drift

        with (
            patch("src.alerts.pipeline.get_last_analysis", new=AsyncMock(return_value=snapshot)),
            patch("src.alerts.pipeline.probe_ticker", new=AsyncMock(return_value=probe)),
            patch(
                "src.alerts.pipeline.check_all_triggers_for_ticker",
                new=AsyncMock(return_value=[]),
            ),
        ):
            outcome = await evaluate_ticker("NVDA")

        assert outcome.evaluated is True
        assert outcome.alert is None
        assert outcome.drift_score == 0.0


class TestEvaluateTickerFullDriftFlow:
    @pytest.mark.asyncio
    async def test_confirmed_drift_persists_and_dispatches(self):
        snapshot = _snapshot(sentiment_score=0.8)
        probe = _probe(sentiment_score=0.1, current_price=85.0)
        events = [
            TriggerEvent(ticker="NVDA", trigger_type="sentiment", summary="dropped"),
            TriggerEvent(ticker="NVDA", trigger_type="price", summary="fell 15%"),
        ]
        judge_result = JudgeResult(
            judgment=DriftJudgment(
                changed=True, new_signal="hold", reasoning="thesis weakened", key_shifts=["x"]
            ),
            llm_invoked=True,
        )

        with (
            patch("src.alerts.pipeline.get_last_analysis", new=AsyncMock(return_value=snapshot)),
            patch("src.alerts.pipeline.probe_ticker", new=AsyncMock(return_value=probe)),
            patch(
                "src.alerts.pipeline.check_all_triggers_for_ticker",
                new=AsyncMock(return_value=events),
            ),
            patch("src.alerts.pipeline.judge_drift", new=AsyncMock(return_value=judge_result)),
            patch("src.alerts.pipeline.persist_alert", new=AsyncMock()) as mock_persist,
            patch(
                "src.alerts.pipeline.dispatch_alert", new=AsyncMock(return_value=2)
            ) as mock_dispatch,
        ):
            outcome = await evaluate_ticker("NVDA")

        assert outcome.alert is not None
        assert outcome.alert.severity == "critical"
        assert outcome.dispatched_to == 2
        mock_persist.assert_called_once()
        mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_false_skips_telegram(self):
        snapshot = _snapshot(sentiment_score=0.8)
        probe = _probe(sentiment_score=0.1, current_price=85.0)
        judge_result = JudgeResult(
            judgment=DriftJudgment(changed=True, new_signal="hold"), llm_invoked=True
        )

        with (
            patch("src.alerts.pipeline.get_last_analysis", new=AsyncMock(return_value=snapshot)),
            patch("src.alerts.pipeline.probe_ticker", new=AsyncMock(return_value=probe)),
            patch(
                "src.alerts.pipeline.check_all_triggers_for_ticker", new=AsyncMock(return_value=[])
            ),
            patch("src.alerts.pipeline.judge_drift", new=AsyncMock(return_value=judge_result)),
            patch("src.alerts.pipeline.persist_alert", new=AsyncMock()),
            patch("src.alerts.pipeline.dispatch_alert", new=AsyncMock()) as mock_dispatch,
        ):
            outcome = await evaluate_ticker("NVDA", dispatch=False)

        assert outcome.dispatched_to == 0
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_failure_does_not_crash_evaluation(self):
        snapshot = _snapshot(sentiment_score=0.8)
        probe = _probe(sentiment_score=0.1, current_price=85.0)
        judge_result = JudgeResult(
            judgment=DriftJudgment(changed=True, new_signal="hold"), llm_invoked=True
        )

        with (
            patch("src.alerts.pipeline.get_last_analysis", new=AsyncMock(return_value=snapshot)),
            patch("src.alerts.pipeline.probe_ticker", new=AsyncMock(return_value=probe)),
            patch(
                "src.alerts.pipeline.check_all_triggers_for_ticker", new=AsyncMock(return_value=[])
            ),
            patch("src.alerts.pipeline.judge_drift", new=AsyncMock(return_value=judge_result)),
            patch(
                "src.alerts.pipeline.persist_alert",
                new=AsyncMock(side_effect=RuntimeError("db down")),
            ),
            patch("src.alerts.pipeline.dispatch_alert", new=AsyncMock(return_value=0)),
        ):
            outcome = await evaluate_ticker("NVDA")

        # Should not raise, alert object still returned
        assert outcome.alert is not None

    @pytest.mark.asyncio
    async def test_budget_exhausted_still_produces_heuristic_alert(self):
        snapshot = _snapshot(sentiment_score=0.8)
        probe = _probe(sentiment_score=0.1, current_price=85.0)
        judge_result = JudgeResult(judgment=None, llm_invoked=False, skip_reason="budget_exhausted")

        with (
            patch("src.alerts.pipeline.get_last_analysis", new=AsyncMock(return_value=snapshot)),
            patch("src.alerts.pipeline.probe_ticker", new=AsyncMock(return_value=probe)),
            patch(
                "src.alerts.pipeline.check_all_triggers_for_ticker", new=AsyncMock(return_value=[])
            ),
            patch("src.alerts.pipeline.judge_drift", new=AsyncMock(return_value=judge_result)),
            patch("src.alerts.pipeline.persist_alert", new=AsyncMock()),
            patch("src.alerts.pipeline.dispatch_alert", new=AsyncMock(return_value=1)),
        ):
            outcome = await evaluate_ticker("NVDA")

        assert outcome.alert is not None
        assert outcome.llm_invoked is False
        assert outcome.alert.severity == "warning"


class TestGetMonitoredTickers:
    @pytest.mark.asyncio
    async def test_unions_portfolio_and_subscriptions_deduped(self):
        with (
            patch(
                "src.mcp_servers.portfolio_server.fetch_all_positions",
                new=AsyncMock(return_value=[{"ticker": "NVDA"}, {"ticker": "AAPL"}]),
            ),
            patch(
                "src.alerts.subscriptions.get_active_subscription_tickers",
                new=AsyncMock(return_value=["AAPL", "TSLA"]),
            ),
        ):
            tickers = await get_monitored_tickers()

        assert tickers == ["NVDA", "AAPL", "TSLA"]

    @pytest.mark.asyncio
    async def test_portfolio_failure_still_returns_subscriptions(self):
        with (
            patch(
                "src.mcp_servers.portfolio_server.fetch_all_positions",
                side_effect=RuntimeError("db down"),
            ),
            patch(
                "src.alerts.subscriptions.get_active_subscription_tickers",
                new=AsyncMock(return_value=["TSLA"]),
            ),
        ):
            tickers = await get_monitored_tickers()

        assert tickers == ["TSLA"]


class TestEvaluateAllMonitored:
    @pytest.mark.asyncio
    async def test_empty_monitored_list_returns_zero_summary(self):
        with patch("src.alerts.pipeline.get_monitored_tickers", new=AsyncMock(return_value=[])):
            summary = await evaluate_all_monitored()

        assert summary.tickers_evaluated == 0
        assert summary.alerts_fired == 0

    @pytest.mark.asyncio
    async def test_aggregates_outcomes_across_tickers(self):
        from src.alerts.composer import Alert
        from src.alerts.pipeline import EvaluationOutcome

        fired_alert = Alert(
            id="a",
            ticker="NVDA",
            alert_type="sentiment",
            severity="critical",
            drift_score=0.6,
            old_signal="buy",
            new_signal="hold",
            reasoning_diff={},
            triggered_by=["sentiment"],
            llm_judged=True,
            created_at=datetime.now(timezone.utc),
        )

        async def _fake_evaluate(ticker, *, correlation_id=None):
            if ticker == "NVDA":
                return EvaluationOutcome(
                    ticker=ticker,
                    evaluated=True,
                    drift_score=0.6,
                    llm_invoked=True,
                    alert=fired_alert,
                )
            return EvaluationOutcome(ticker=ticker, evaluated=True, drift_score=0.1)

        with (
            patch(
                "src.alerts.pipeline.get_monitored_tickers",
                new=AsyncMock(return_value=["NVDA", "AAPL"]),
            ),
            patch("src.alerts.pipeline.evaluate_ticker", side_effect=_fake_evaluate),
        ):
            summary = await evaluate_all_monitored()

        assert summary.tickers_evaluated == 2
        assert summary.alerts_fired == 1
        assert summary.llm_calls_used == 1

    @pytest.mark.asyncio
    async def test_per_ticker_exception_does_not_abort_run(self):
        async def _side_effect(ticker, **_kwargs):
            if ticker == "BAD":
                raise RuntimeError("boom")
            return await _ok_outcome(ticker)

        with (
            patch(
                "src.alerts.pipeline.get_monitored_tickers",
                new=AsyncMock(return_value=["GOOD", "BAD"]),
            ),
            patch("src.alerts.pipeline.evaluate_ticker", side_effect=_side_effect),
        ):
            summary = await evaluate_all_monitored()

        assert summary.tickers_evaluated == 2


async def _ok_outcome(ticker):
    from src.alerts.pipeline import EvaluationOutcome

    return EvaluationOutcome(ticker=ticker, evaluated=True, drift_score=0.0)
