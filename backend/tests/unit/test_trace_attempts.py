"""LLM attempt records are stored with the trace and read back with it."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.ops import trace_recorder

ATTEMPTS = [
    {
        "role": "bear",
        "model": "nvidia/x",
        "mode": "reasoning_on",
        "outcome": "timeout",
        "elapsed_s": 45.0,
    },
    {
        "role": "bear",
        "model": "nvidia/x",
        "mode": "reasoning_off",
        "outcome": "ok",
        "elapsed_s": 9.8,
    },
]


@pytest.mark.asyncio
async def test_record_trace_stores_the_attempts_as_json():
    pool = AsyncMock()
    with patch.object(trace_recorder, "get_pool", AsyncMock(return_value=pool)):
        await trace_recorder.record_trace(
            "run-1", ["NVDA"], [{"type": "x"}], 1234, "degraded", "hold", llm_attempts=ATTEMPTS
        )
    args = pool.execute.await_args.args
    assert "llm_attempts" in args[0]
    assert json.loads(args[-1]) == ATTEMPTS


@pytest.mark.asyncio
async def test_record_trace_without_attempts_stores_null():
    pool = AsyncMock()
    with patch.object(trace_recorder, "get_pool", AsyncMock(return_value=pool)):
        await trace_recorder.record_trace("run-1", ["NVDA"], [], 10, "success")
    assert pool.execute.await_args.args[-1] is None


def _row(**extra):
    base = {
        "id": "b3c0a7e2-1111-4222-8333-444455556666",
        "run_id": "run-1",
        "tickers": ["NVDA"],
        "events": "[]",
        "duration_ms": 10,
        "status": "success",
        "signal": "hold",
        "created_at": datetime(2026, 10, 22, tzinfo=timezone.utc),
    }
    base.update(extra)
    return base


def test_trace_row_decodes_attempts():
    out = trace_recorder._row_to_trace(_row(llm_attempts=json.dumps(ATTEMPTS)))
    assert out["llm_attempts"] == ATTEMPTS


def test_trace_row_without_the_column_still_loads():
    # Rows written before the column existed, or queries that do not select it.
    out = trace_recorder._row_to_trace(_row())
    assert out["llm_attempts"] is None


def test_trace_row_with_null_attempts():
    assert trace_recorder._row_to_trace(_row(llm_attempts=None))["llm_attempts"] is None
