"""
Regression tests for per-ticker cost attribution run isolation.

Sessions are keyed by (run_id, ticker) so two concurrent analyses that both
include the same ticker don't overwrite each other's accumulated token counts
or let one run's flush pop the other's record.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.ops.cost_attribution import CostAttributor


def test_same_ticker_distinct_runs_are_isolated():
    attr = CostAttributor()
    attr.start_analysis("AAPL", run_id="run-a")
    attr.start_analysis("AAPL", run_id="run-b")

    attr.record_llm_call("AAPL", "analysis", 100, 50, run_id="run-a")
    attr.record_llm_call("AAPL", "analysis", 999, 999, run_id="run-b")

    rec_a = attr._current_session[("run-a", "AAPL")]
    rec_b = attr._current_session[("run-b", "AAPL")]

    assert rec_a.input_tokens == 100
    assert rec_a.output_tokens == 50
    assert rec_b.input_tokens == 999
    assert rec_b.output_tokens == 999


@pytest.mark.asyncio
async def test_flush_pops_only_its_own_run():
    attr = CostAttributor()
    attr.start_analysis("AAPL", run_id="run-a")
    attr.start_analysis("AAPL", run_id="run-b")
    attr.record_llm_call("AAPL", "analysis", 10, 10, run_id="run-a")
    attr.record_llm_call("AAPL", "analysis", 20, 20, run_id="run-b")

    with patch("src.ops.cost_attribution.execute", new_callable=AsyncMock):
        flushed = await attr.flush("AAPL", correlation_id="run-a", run_id="run-a")

    assert flushed is not None
    assert flushed.input_tokens == 10
    # run-b's record must survive run-a's flush.
    assert ("run-b", "AAPL") in attr._current_session
    assert ("run-a", "AAPL") not in attr._current_session


@pytest.mark.asyncio
async def test_flush_unknown_run_returns_none():
    attr = CostAttributor()
    with patch("src.ops.cost_attribution.execute", new_callable=AsyncMock):
        result = await attr.flush("AAPL", run_id="missing")
    assert result is None


def test_record_without_start_autocreates_scoped_record():
    attr = CostAttributor()
    attr.record_llm_call("NVDA", "router", 5, 5, run_id="run-x")
    assert ("run-x", "NVDA") in attr._current_session
    assert ("", "NVDA") not in attr._current_session
