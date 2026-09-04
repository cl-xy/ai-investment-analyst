"""
Tests for the LLM drift judge (Tier 2 of the alert pipeline).
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.alerts.drift_judge import DriftJudgment, judge_drift
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


def _ai_message(payload: dict) -> AIMessage:
    return AIMessage(content=json.dumps(payload))


class TestDriftJudgment:
    def test_normalizes_signal_case(self):
        judgment = DriftJudgment.model_validate({"changed": True, "new_signal": "SELL"})
        assert judgment.new_signal == "sell"

    def test_invalid_signal_becomes_empty(self):
        judgment = DriftJudgment.model_validate({"changed": False, "new_signal": "bullish"})
        assert judgment.new_signal == ""

    def test_coerces_non_string_key_shifts(self):
        judgment = DriftJudgment.model_validate({"changed": True, "key_shifts": [1, "ok", None]})
        assert judgment.key_shifts == ["1", "ok"]


class TestJudgeDriftGoldenFixture:
    @pytest.mark.asyncio
    async def test_contradicted_thesis_confirms_change(self):
        events = [
            TriggerEvent(
                ticker="NVDA",
                trigger_type="sentiment",
                summary="Retail sentiment deteriorated: 0.70 -> 0.10",
            ),
            TriggerEvent(
                ticker="NVDA",
                trigger_type="sec_filing",
                summary="New 8-K filed on 2026-08-15",
            ),
        ]
        mock_response = _ai_message(
            {
                "changed": True,
                "new_signal": "hold",
                "reasoning": "Sentiment collapse and new filing undermine the bull thesis.",
                "key_shifts": ["sentiment reversal", "new material 8-K"],
            }
        )

        with (
            patch("src.alerts.drift_judge.use_budget", new=AsyncMock(return_value=True)),
            patch(
                "src.alerts.drift_judge.invoke_with_fallback",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            result = await judge_drift("NVDA", _snapshot(), events)

        assert result.llm_invoked is True
        assert result.judgment is not None
        assert result.judgment.changed is True
        assert result.judgment.new_signal == "hold"
        assert len(result.judgment.key_shifts) == 2

    @pytest.mark.asyncio
    async def test_noise_confirms_no_change(self):
        events = [
            TriggerEvent(ticker="NVDA", trigger_type="price", summary="Price moved down 5.2%")
        ]
        mock_response = _ai_message(
            {
                "changed": False,
                "new_signal": "",
                "reasoning": "Minor price noise, thesis intact.",
                "key_shifts": [],
            }
        )

        with (
            patch("src.alerts.drift_judge.use_budget", new=AsyncMock(return_value=True)),
            patch(
                "src.alerts.drift_judge.invoke_with_fallback",
                new=AsyncMock(return_value=mock_response),
            ),
        ):
            result = await judge_drift("NVDA", _snapshot(), events)

        assert result.judgment.changed is False
        assert result.judgment.new_signal == ""


class TestJudgeDriftBudgetGate:
    @pytest.mark.asyncio
    async def test_skips_llm_call_when_budget_exhausted(self):
        llm_mock = AsyncMock()
        with (
            patch("src.alerts.drift_judge.use_budget", new=AsyncMock(return_value=False)),
            patch("src.alerts.drift_judge.invoke_with_fallback", new=llm_mock),
        ):
            result = await judge_drift("NVDA", _snapshot(), [])

        assert result.llm_invoked is False
        assert result.judgment is None
        assert result.skip_reason == "budget_exhausted"
        llm_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_checks_openrouter_budget_specifically(self):
        budget_mock = AsyncMock(return_value=True)
        with (
            patch("src.alerts.drift_judge.use_budget", new=budget_mock),
            patch(
                "src.alerts.drift_judge.invoke_with_fallback",
                new=AsyncMock(return_value=_ai_message({"changed": False})),
            ),
        ):
            await judge_drift("NVDA", _snapshot(), [])

        budget_mock.assert_called_once_with("openrouter")


class TestJudgeDriftErrorHandling:
    @pytest.mark.asyncio
    async def test_malformed_json_response_falls_back_gracefully(self):
        bad_response = AIMessage(content="not json at all")
        with (
            patch("src.alerts.drift_judge.use_budget", new=AsyncMock(return_value=True)),
            patch(
                "src.alerts.drift_judge.invoke_with_fallback",
                new=AsyncMock(return_value=bad_response),
            ),
        ):
            result = await judge_drift("NVDA", _snapshot(), [])

        assert result.judgment is None
        assert result.llm_invoked is True
        assert result.skip_reason == "parse_failed"

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back_gracefully(self):
        with (
            patch("src.alerts.drift_judge.use_budget", new=AsyncMock(return_value=True)),
            patch(
                "src.alerts.drift_judge.invoke_with_fallback",
                new=AsyncMock(side_effect=RuntimeError("provider down")),
            ),
        ):
            result = await judge_drift("NVDA", _snapshot(), [])

        assert result.judgment is None
        assert result.skip_reason == "llm_call_failed"

    @pytest.mark.asyncio
    async def test_uses_router_model_not_debate_model(self):
        """The judge must use the cheap/fast router model, not the 120B debate model."""
        from src.config import settings

        captured_kwargs = {}

        async def _capture(*_args, **kwargs):
            captured_kwargs.update(kwargs)
            return _ai_message({"changed": False})

        with (
            patch("src.alerts.drift_judge.use_budget", new=AsyncMock(return_value=True)),
            patch("src.alerts.drift_judge.invoke_with_fallback", side_effect=_capture),
        ):
            await judge_drift("NVDA", _snapshot(), [])

        assert captured_kwargs["primary_model"] == settings.llm_router_model
        assert captured_kwargs["fallback_model"] == settings.llm_router_model_fallback
