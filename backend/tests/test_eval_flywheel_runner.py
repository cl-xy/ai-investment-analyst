"""
Regression tests for the bounded evaluation runner's persistence boundary.

Focus: the evaluation_results.status CHECK constraint only permits
('completed','schema_failed','timeout','error'), but replay can emit
'not_replayable'. The runner must map that to 'error' at the INSERT (keeping
the reason in the error column) so a single non-replayable case cannot abort
the run with a CHECK violation and strand the evaluation_runs row in 'running'.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.eval_flywheel.replay import BatchReplayResult, ReplayResult
from src.eval_flywheel.runner import run_bounded_evaluation


def _result_inserts(execute_mock: AsyncMock) -> list[tuple]:
    """All execute() calls that INSERT into evaluation_results."""
    return [
        call.args
        for call in execute_mock.await_args_list
        if "INSERT INTO evaluation_results" in call.args[0]
    ]


def _run_updates(execute_mock: AsyncMock) -> list[tuple]:
    return [
        call.args
        for call in execute_mock.await_args_list
        if "UPDATE evaluation_runs" in call.args[0]
    ]


@pytest.mark.asyncio
async def test_not_replayable_persists_as_error_and_run_completes():
    cases = [
        {
            "case_id": "11111111-1111-1111-1111-111111111111",
            "ticker": "NVDA",
            "signal": "buy",
            "confidence": "high",
            "outcome": "correct",
            "realized_return": 0.1,
            "excess_return": 0.05,
        }
    ]
    batch = BatchReplayResult(
        results=[
            ReplayResult(
                case_id=cases[0]["case_id"],
                status="not_replayable",
                error="capture_status is not 'complete' or no artifacts found",
            )
        ]
    )

    with (
        patch("src.eval_flywheel.runner.fetch", new_callable=AsyncMock, return_value=cases),
        patch(
            "src.eval_flywheel.runner.fetchrow",
            new_callable=AsyncMock,
            return_value={"id": "22222222-2222-2222-2222-222222222222"},
        ),
        patch("src.eval_flywheel.runner.execute", new_callable=AsyncMock) as mock_execute,
        patch(
            "src.eval_flywheel.runner.replay_cases_batch",
            new_callable=AsyncMock,
            return_value=batch,
        ),
    ):
        summary = await run_bounded_evaluation(max_cases=20)

    # The per-case INSERT must carry an allowed status, not 'not_replayable'.
    inserts = _result_inserts(mock_execute)
    assert len(inserts) == 1
    status_arg = inserts[0][3]  # VALUES ($1 run_id, $2 case_id, $3 status, ...)
    assert status_arg == "error"
    error_arg = inserts[0][8]
    assert error_arg and "not_replayable" in error_arg or "complete" in error_arg

    # The run must have been finalized (completed), not stranded in 'running'.
    updates = _run_updates(mock_execute)
    assert any("status = 'completed'" in u[0] for u in updates)
    assert summary["run_id"] == "22222222-2222-2222-2222-222222222222"


@pytest.mark.asyncio
async def test_run_marked_failed_when_persistence_raises():
    """Any unexpected error after the 'running' row is created must flip the
    run to 'failed' (an allowed status) rather than leaving it 'running'."""
    cases = [
        {
            "case_id": "33333333-3333-3333-3333-333333333333",
            "ticker": "AAPL",
            "signal": "hold",
            "confidence": "low",
            "outcome": "neutral",
            "realized_return": 0.0,
            "excess_return": 0.0,
        }
    ]
    batch = BatchReplayResult(
        results=[ReplayResult(case_id=cases[0]["case_id"], status="completed", output={})]
    )

    calls = {"n": 0}

    async def _execute(sql, *args):
        # Fail the per-case INSERT; allow the failure UPDATE to go through.
        if "INSERT INTO evaluation_results" in sql:
            calls["n"] += 1
            raise RuntimeError("simulated db failure")
        return None

    with (
        patch("src.eval_flywheel.runner.fetch", new_callable=AsyncMock, return_value=cases),
        patch(
            "src.eval_flywheel.runner.fetchrow",
            new_callable=AsyncMock,
            return_value={"id": "44444444-4444-4444-4444-444444444444"},
        ),
        patch("src.eval_flywheel.runner.execute", side_effect=_execute) as mock_execute,
        patch(
            "src.eval_flywheel.runner.replay_cases_batch",
            new_callable=AsyncMock,
            return_value=batch,
        ),
    ):
        with pytest.raises(RuntimeError):
            await run_bounded_evaluation(max_cases=20)

    updates = _run_updates(mock_execute)
    assert any("status = 'failed'" in u[0] for u in updates)
