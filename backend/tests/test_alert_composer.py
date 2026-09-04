"""
Tests for alert composition and persistence.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.alerts.composer import compose_alert, get_alert, mark_alert_dispatched, persist_alert
from src.alerts.drift_judge import DriftJudgment
from src.alerts.drift_scorer import score_drift
from src.alerts.last_analysis import LastAnalysisSnapshot
from src.alerts.triggers.events import TriggerEvent


def _snapshot(**overrides) -> LastAnalysisSnapshot:
    defaults = dict(
        ticker="NVDA",
        signal="buy",
        confidence="high",
        sentiment_score=0.7,
        risk_flags=["supply chain"],
        price_data={"currentPrice": 120.0},
        fundamentals={"sector": "Technology"},
        analysis_id="test-id",
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return LastAnalysisSnapshot(**defaults)


class TestComposeAlertSeverity:
    def test_llm_confirmed_change_is_critical(self):
        drift = score_drift(previous_sentiment=0.8, current_sentiment=0.1)
        judgment = DriftJudgment(changed=True, new_signal="hold", reasoning="x", key_shifts=["a"])
        alert = compose_alert("NVDA", _snapshot(), drift, [], judgment, llm_invoked=True)
        assert alert.severity == "critical"
        assert alert.new_signal == "hold"

    def test_llm_rejected_change_is_warning(self):
        drift = score_drift(previous_sentiment=0.8, current_sentiment=0.1)
        judgment = DriftJudgment(changed=False, new_signal="", reasoning="noise", key_shifts=[])
        alert = compose_alert("NVDA", _snapshot(), drift, [], judgment, llm_invoked=True)
        assert alert.severity == "warning"
        assert alert.new_signal is None

    def test_budget_exhausted_high_score_is_warning(self):
        drift = score_drift(previous_sentiment=0.8, current_sentiment=0.1, threshold=0.1)
        alert = compose_alert("NVDA", _snapshot(), drift, [], None, llm_invoked=False)
        assert alert.severity == "warning"

    def test_budget_exhausted_low_score_is_info(self):
        drift = score_drift(previous_sentiment=0.5, current_sentiment=0.52)
        alert = compose_alert("NVDA", _snapshot(), drift, [], None, llm_invoked=False)
        assert alert.severity == "info"

    def test_llm_parse_failure_falls_back_to_heuristic_severity(self):
        drift = score_drift(previous_sentiment=0.8, current_sentiment=0.1, threshold=0.1)
        alert = compose_alert("NVDA", _snapshot(), drift, [], None, llm_invoked=True)
        assert alert.severity == "warning"
        assert alert.llm_judged is False


class TestComposeAlertContent:
    def test_alert_type_prioritizes_sec_filing(self):
        drift = score_drift()
        events = [
            TriggerEvent(ticker="NVDA", trigger_type="price", summary="p"),
            TriggerEvent(ticker="NVDA", trigger_type="sec_filing", summary="f"),
        ]
        alert = compose_alert("NVDA", _snapshot(), drift, events, None, llm_invoked=False)
        assert alert.alert_type == "sec_filing"

    def test_alert_type_falls_back_to_drift_score_when_no_events(self):
        drift = score_drift()
        alert = compose_alert("NVDA", _snapshot(), drift, [], None, llm_invoked=False)
        assert alert.alert_type == "drift_score"

    def test_reasoning_diff_includes_components_and_events(self):
        drift = score_drift(previous_sentiment=0.8, current_sentiment=0.1)
        events = [TriggerEvent(ticker="NVDA", trigger_type="sentiment", summary="dropped")]
        alert = compose_alert("NVDA", _snapshot(), drift, events, None, llm_invoked=False)
        assert "components" in alert.reasoning_diff
        assert alert.reasoning_diff["triggered_events"][0]["summary"] == "dropped"
        assert alert.reasoning_diff["prior_signal"] == "buy"

    def test_reasoning_diff_includes_llm_judgment_when_present(self):
        drift = score_drift(previous_sentiment=0.8, current_sentiment=0.1)
        judgment = DriftJudgment(
            changed=True, new_signal="sell", reasoning="thesis broken", key_shifts=["x", "y"]
        )
        alert = compose_alert("NVDA", _snapshot(), drift, [], judgment, llm_invoked=True)
        assert alert.reasoning_diff["llm_judgment"]["new_signal"] == "sell"
        assert alert.reasoning_diff["llm_judgment"]["key_shifts"] == ["x", "y"]

    def test_alert_has_valid_uuid_and_ticker(self):
        drift = score_drift()
        alert = compose_alert("AAPL", _snapshot(ticker="AAPL"), drift, [], None, llm_invoked=False)
        uuid.UUID(alert.id)  # raises if invalid
        assert alert.ticker == "AAPL"


class TestPersistenceRoundTrip:
    @pytest.mark.asyncio
    async def test_persist_alert_calls_execute_with_serialized_fields(self):
        drift = score_drift(previous_sentiment=0.8, current_sentiment=0.1)
        events = [TriggerEvent(ticker="NVDA", trigger_type="sentiment", summary="dropped")]
        alert = compose_alert("NVDA", _snapshot(), drift, events, None, llm_invoked=False)

        with patch("src.alerts.composer.execute", new=AsyncMock()) as mock_execute:
            await persist_alert(alert)

        mock_execute.assert_called_once()
        args = mock_execute.call_args.args
        # args[0] is the SQL string; verify params include serialized JSON
        assert args[2] == alert.ticker
        reasoning_diff_json = args[8]
        parsed = json.loads(reasoning_diff_json)
        assert parsed["prior_signal"] == "buy"

    @pytest.mark.asyncio
    async def test_get_alert_returns_none_when_missing(self):
        with patch("src.alerts.composer.fetchrow", new=AsyncMock(return_value=None)):
            result = await get_alert(str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_alert_returns_row_as_dict(self):
        fake_row = {"id": uuid.uuid4(), "ticker": "NVDA", "severity": "critical"}
        with patch("src.alerts.composer.fetchrow", new=AsyncMock(return_value=fake_row)):
            result = await get_alert(str(uuid.uuid4()))
        assert result["ticker"] == "NVDA"

    @pytest.mark.asyncio
    async def test_mark_alert_dispatched_calls_update(self):
        alert_id = str(uuid.uuid4())
        with patch("src.alerts.composer.execute", new=AsyncMock()) as mock_execute:
            await mark_alert_dispatched(alert_id)
        mock_execute.assert_called_once()
        assert "UPDATE alerts" in mock_execute.call_args.args[0]
