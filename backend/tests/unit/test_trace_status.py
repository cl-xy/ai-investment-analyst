"""A run whose debate fell back to a degraded partial must not be recorded as success."""

from types import SimpleNamespace

from src.api.routes.analyze_stream import _trace_status


def _tool_event(no_data=False):
    return SimpleNamespace(type=SimpleNamespace(value="tool_result"), payload={"no_data": no_data})


def test_clean_run_is_success():
    analyses = {"NVDA": {"debate_status": "complete"}}
    assert _trace_status(True, [_tool_event()], analyses) == "success"


def test_missing_debate_status_counts_as_complete():
    # Rows that predate the field have no debate_status.
    assert _trace_status(True, [], {"NVDA": {}}) == "success"


def test_degraded_moderator_is_not_a_success():
    analyses = {"NVDA": {"debate_status": "degraded_moderator"}}
    assert _trace_status(True, [_tool_event()], analyses) == "degraded"


def test_any_degraded_ticker_degrades_a_multi_ticker_run():
    analyses = {"NVDA": {"debate_status": "complete"}, "AAPL": {"debate_status": "degraded_bear"}}
    assert _trace_status(True, [], analyses) == "degraded"


def test_tool_with_no_data_degrades_the_run():
    assert (
        _trace_status(True, [_tool_event(no_data=True)], {"NVDA": {"debate_status": "complete"}})
        == "degraded"
    )


def test_failed_run_stays_failed():
    assert _trace_status(False, [], {"NVDA": {"debate_status": "degraded_bull"}}) == "failed"
