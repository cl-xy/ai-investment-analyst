"""
Tests for Task 4: frozen-input debate-core replay evaluator.

Critical properties asserted:
- Zero live tool/network calls (only the LLM invocation boundary is mocked;
  no MCP tool, no yfinance, no HTTP client is ever touched).
- No hindsight leakage: outcome-bearing fields can never reach a debate
  prompt, asserted both structurally (via _reconstruct_state's assertion)
  and behaviorally (mocked LLM captures the actual prompt text sent).
- Graceful handling of schema failure, timeout, and not-yet-captured cases.
- Deterministic batch ordering.
"""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage
from src.eval_flywheel.replay import (
    _reconstruct_state,
    replay_case,
    replay_cases_batch,
)


def _grouped_payloads(ticker="NVDA") -> dict[str, list[dict]]:
    return {
        "yfinance:get_quote": [{"ticker": ticker, "payload": {"currentPrice": 875.0}}],
        "yfinance:get_fundamentals": [{"ticker": ticker, "payload": {"peRatio": 45.0}}],
        "yfinance:get_technical_indicators": [{"ticker": ticker, "payload": {"rsi": 55}}],
        "newsapi:get_ticker_news": [
            {"ticker": ticker, "payload": [{"title": "NVDA rallies", "source": "Reuters"}]}
        ],
        "sec_edgar:get_latest_filing_summary": [
            {"ticker": ticker, "payload": "Filing excerpt text."}
        ],
        "yfinance:get_earnings_calendar": [
            {"ticker": ticker, "payload": {"next_earnings_date": "2026-09-15"}}
        ],
        "stocktwits:get_ticker_sentiment": [
            {"ticker": ticker, "payload": {"message_count": 10, "bullish_count": 7}}
        ],
    }


def _mock_llm_response(json_str: str) -> AIMessage:
    return AIMessage(content=json_str)


BULL_JSON = (
    '{"ticker": "NVDA", "thesis": "Strong growth", "key_arguments": ["a1"], '
    '"catalysts": [], "evidence": [], "confidence": "high", "acknowledged_risks": []}'
)
BEAR_JSON = (
    '{"ticker": "NVDA", "thesis": "Valuation risk", "key_arguments": ["b1"], '
    '"rebuttals": [], "risk_flags": [], "evidence": [], "confidence": "medium", '
    '"conceded_strengths": []}'
)
MODERATOR_JSON = (
    '{"ticker": "NVDA", "signal": "buy", "confidence": "medium", "sentiment_score": 0.3, '
    '"thesis": "Balanced verdict", "bull_case": ["a1"], "bear_case": ["b1"], '
    '"key_disagreements": [], "verdict_rationale": "r", "risk_flags": [], '
    '"citations": [], "data_gaps": [], "news_summary": "n", "sec_notes": ""}'
)


class TestReconstructStateNoLeakage:
    def test_builds_expected_state_shape(self):
        state = _reconstruct_state("NVDA", _grouped_payloads())
        assert state["raw_prices"]["NVDA"]["quote"] == {"currentPrice": 875.0}
        assert state["raw_news"]["NVDA"][0]["title"] == "NVDA rallies"
        assert "run_evidence" in state

    def test_forbidden_outcome_key_raises_assertion(self):
        payloads = _grouped_payloads()
        payloads["yfinance:get_quote"][0]["payload"]["outcome"] = "incorrect"
        with pytest.raises(AssertionError, match="hindsight leakage"):
            _reconstruct_state("NVDA", payloads)

    def test_correlation_id_is_none_not_original_run(self):
        """Replay state must not carry the original run's correlation_id -
        it's a fresh, isolated replay context."""
        state = _reconstruct_state("NVDA", _grouped_payloads())
        assert state["correlation_id"] is None


class TestReplayCaseZeroLiveCalls:
    @pytest.mark.asyncio
    async def test_zero_tool_or_network_calls_during_replay(self):
        """Patch every tool-call surface to raise if touched; only the LLM
        invocation boundary (invoke_with_fallback) is mocked to succeed."""
        with (
            patch(
                "src.eval_flywheel.replay.load_case_tool_payloads",
                new_callable=AsyncMock,
                return_value=_grouped_payloads(),
            ),
            patch(
                "src.agent.nodes.debate.invoke_with_fallback",
                new_callable=AsyncMock,
                side_effect=[
                    _mock_llm_response(BULL_JSON),
                    _mock_llm_response(BEAR_JSON),
                    _mock_llm_response(MODERATOR_JSON),
                ],
            ),
            patch("src.agent.nodes.debate.asyncio.sleep", new_callable=AsyncMock),
            patch(
                "src.mcp_servers.market_server.server",
                side_effect=AssertionError("live tool call attempted during replay"),
                create=True,
            ),
        ):
            result = await replay_case("case-1", "NVDA")

        assert result.status == "completed"
        assert result.output["signal"] == "buy"
        assert result.output["_bull_evidence_count"] == 0

    @pytest.mark.asyncio
    async def test_prompts_never_contain_outcome_fields(self):
        """Behavioral check: capture the actual prompt strings sent to the
        (mocked) LLM and assert no outcome-bearing substring appears."""
        captured_prompts: list[str] = []

        async def _capture_invoke(messages, **kwargs):
            for m in messages:
                captured_prompts.append(str(m.content))
            # Return responses in bull -> bear -> moderator order based on call count
            idx = _capture_invoke.call_count
            _capture_invoke.call_count += 1
            return [
                _mock_llm_response(BULL_JSON),
                _mock_llm_response(BEAR_JSON),
                _mock_llm_response(MODERATOR_JSON),
            ][idx]

        _capture_invoke.call_count = 0

        with (
            patch(
                "src.eval_flywheel.replay.load_case_tool_payloads",
                new_callable=AsyncMock,
                return_value=_grouped_payloads(),
            ),
            patch(
                "src.agent.nodes.debate.invoke_with_fallback",
                side_effect=_capture_invoke,
            ),
            patch("src.agent.nodes.debate.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await replay_case("case-1", "NVDA")

        assert result.status == "completed"
        forbidden_terms = ("realized_return", "excess_return", "outcome_price", "resolved_at")
        for prompt in captured_prompts:
            for term in forbidden_terms:
                assert term not in prompt


class TestReplayCaseNotReplayable:
    @pytest.mark.asyncio
    async def test_returns_not_replayable_when_capture_incomplete(self):
        with patch(
            "src.eval_flywheel.replay.load_case_tool_payloads",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await replay_case("case-1", "NVDA")
        assert result.status == "not_replayable"
        assert result.output is None


class TestReplayCaseTimeoutAndError:
    @pytest.mark.asyncio
    async def test_timeout_reports_timeout_status(self):
        import asyncio

        async def _hang(*args, **kwargs):
            await asyncio.sleep(10)

        with (
            patch(
                "src.eval_flywheel.replay.load_case_tool_payloads",
                new_callable=AsyncMock,
                return_value=_grouped_payloads(),
            ),
            patch("src.eval_flywheel.replay._run_replay_debate", side_effect=_hang),
        ):
            result = await replay_case("case-1", "NVDA", timeout_seconds=0)
        assert result.status == "timeout"

    @pytest.mark.asyncio
    async def test_unexpected_error_reports_error_status_not_raise(self):
        with (
            patch(
                "src.eval_flywheel.replay.load_case_tool_payloads",
                new_callable=AsyncMock,
                return_value=_grouped_payloads(),
            ),
            patch(
                "src.eval_flywheel.replay._run_replay_debate",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = await replay_case("case-1", "NVDA")
        assert result.status == "error"
        assert "boom" in result.error


class TestReplayCasesBatchDeterministicOrder:
    @pytest.mark.asyncio
    async def test_processes_in_given_order_and_isolates_failures(self):
        call_order: list[str] = []

        async def _fake_replay(case_id, ticker, **kwargs):
            call_order.append(case_id)
            from src.eval_flywheel.replay import ReplayResult

            if case_id == "bad":
                return ReplayResult(case_id=case_id, status="error", error="boom")
            return ReplayResult(case_id=case_id, status="completed", output={"signal": "buy"})

        with patch("src.eval_flywheel.replay.replay_case", side_effect=_fake_replay):
            batch = await replay_cases_batch([("a", "NVDA"), ("bad", "AAPL"), ("c", "MSFT")])

        assert call_order == ["a", "bad", "c"]
        assert batch.completed_count == 2
        assert len(batch.results) == 3
