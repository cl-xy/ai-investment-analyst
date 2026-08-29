"""
Outcome-Grounded Evaluation Flywheel: read API + bounded trigger endpoint.

Read endpoints are public-shaped but gated by the existing DemoAuthMiddleware
(this prefix is added to PROTECTED_PREFIXES, matching /api/calibration and
/api/eval). The trigger endpoint additionally requires the scheduler token,
matching the pattern in routes/scheduled.py, since it can consume LLM budget.
"""

from __future__ import annotations

import logging
from secrets import compare_digest

from fastapi import APIRouter, Header, HTTPException, Query

from src.config import settings
from src.db import fetch, fetchrow, fetchval

log = logging.getLogger(__name__)

router = APIRouter(prefix="/eval-flywheel", tags=["eval-flywheel"])


@router.get("/funnel")
async def get_funnel():
    """Funnel counts: resolved predictions -> classified -> promoted -> captured."""
    resolved_total = await fetchval(
        "SELECT COUNT(*) FROM predictions WHERE resolved_at IS NOT NULL"
    )
    classified_total = await fetchval("SELECT COUNT(*) FROM evaluation_cases")
    promoted_total = await fetchval(
        "SELECT COUNT(*) FROM evaluation_cases WHERE state = 'promoted'"
    )
    capture_complete_total = await fetchval(
        "SELECT COUNT(*) FROM evaluation_cases WHERE state = 'promoted' AND capture_status = 'complete'"
    )

    reason_rows = await fetch(
        """
        SELECT jsonb_array_elements_text(promotion_reasons) AS reason, COUNT(*) AS count
        FROM evaluation_cases
        WHERE state = 'promoted'
        GROUP BY reason
        ORDER BY count DESC
        """
    )

    return {
        "resolved_predictions": resolved_total or 0,
        "classified_cases": classified_total or 0,
        "promoted_cases": promoted_total or 0,
        "replay_ready_cases": capture_complete_total or 0,
        "promotion_reasons": [{"reason": r["reason"], "count": r["count"]} for r in reason_rows],
    }


@router.get("/cases")
async def list_cases(
    state: str | None = Query(None, description="Filter by case state"),
    ticker: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List evaluation cases with optional filters."""
    conditions: list[str] = []
    params: list[object] = []
    idx = 1

    if state:
        if state not in ("candidate", "promoted", "excluded", "retired"):
            raise HTTPException(status_code=400, detail=f"Invalid state: {state!r}")
        conditions.append(f"state = ${idx}")
        params.append(state)
        idx += 1

    if ticker:
        conditions.append(f"ticker = ${idx}")
        params.append(ticker.upper())
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    rows = await fetch(  # nosemgrep: sql-string-interpolation
        f"""
        SELECT id, prediction_id, analysis_id, ticker, state, promotion_reasons,
               capture_status, created_at, updated_at
        FROM evaluation_cases
        {where}
        ORDER BY created_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *params,
    )

    total = await fetchval(  # nosemgrep: sql-string-interpolation
        f"SELECT COUNT(*) FROM evaluation_cases {where}",
        *params[:-2],
    )

    return {
        "cases": [_case_row_to_dict(r) for r in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/cases/{case_id}")
async def get_case_detail(case_id: str):
    """Full detail for one evaluation case, including its linked prediction
    and (if captured) artifact summary. Does not return full_payload content
    — that is replay input, not a UI-facing field, and can be large."""
    case_row = await fetchrow(
        """
        SELECT id, prediction_id, analysis_id, ticker, state, promotion_reasons,
               capture_status, created_at, updated_at
        FROM evaluation_cases WHERE id = $1
        """,
        case_id,
    )
    if not case_row:
        raise HTTPException(status_code=404, detail="Evaluation case not found")

    prediction_row = await fetchrow(
        """
        SELECT id, ticker, signal, confidence, outcome, realized_return,
               excess_return, created_at, resolved_at
        FROM predictions WHERE id = $1
        """,
        case_row["prediction_id"],
    )

    artifact_rows = await fetch(
        """
        SELECT provider, tool, ticker, payload_size
        FROM evaluation_case_artifacts WHERE case_id = $1
        ORDER BY provider, tool
        """,
        case_id,
    )

    return {
        "case": _case_row_to_dict(case_row),
        "prediction": (
            {
                "id": str(prediction_row["id"]),
                "ticker": prediction_row["ticker"],
                "signal": prediction_row["signal"],
                "confidence": prediction_row["confidence"],
                "outcome": prediction_row["outcome"],
                "realized_return": prediction_row["realized_return"],
                "excess_return": prediction_row["excess_return"],
                "created_at": prediction_row["created_at"].isoformat()
                if prediction_row["created_at"]
                else None,
                "resolved_at": prediction_row["resolved_at"].isoformat()
                if prediction_row["resolved_at"]
                else None,
            }
            if prediction_row
            else None
        ),
        "artifacts": [
            {
                "provider": r["provider"],
                "tool": r["tool"],
                "ticker": r["ticker"],
                "payload_size": r["payload_size"],
            }
            for r in artifact_rows
        ],
    }


@router.get("/runs")
async def list_runs(limit: int = Query(20, ge=1, le=100)):
    """Evaluation run history (baseline-vs-candidate comparison runs)."""
    rows = await fetch(
        """
        SELECT id, candidate_config, corpus_version, case_count, started_at,
               completed_at, status, decision, aggregate_scores,
               budget_tokens_used, budget_llm_calls
        FROM evaluation_runs
        ORDER BY started_at DESC
        LIMIT $1
        """,
        limit,
    )
    return {"runs": [_run_row_to_dict(r) for r in rows]}


@router.get("/runs/{run_id}")
async def get_run_detail(run_id: str):
    """Full detail for one evaluation run, including per-case results."""
    run_row = await fetchrow(
        """
        SELECT id, candidate_config, corpus_version, case_count, started_at,
               completed_at, status, decision, aggregate_scores,
               budget_tokens_used, budget_llm_calls
        FROM evaluation_runs WHERE id = $1
        """,
        run_id,
    )
    if not run_row:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    result_rows = await fetch(
        """
        SELECT id, case_id, status, baseline_scores, candidate_scores,
               latency_ms, tokens_used, error, created_at
        FROM evaluation_results WHERE run_id = $1
        ORDER BY created_at ASC
        """,
        run_id,
    )

    return {
        "run": _run_row_to_dict(run_row),
        "results": [
            {
                "id": str(r["id"]),
                "case_id": str(r["case_id"]),
                "status": r["status"],
                "baseline_scores": r["baseline_scores"],
                "candidate_scores": r["candidate_scores"],
                "latency_ms": r["latency_ms"],
                "tokens_used": r["tokens_used"],
                "error": r["error"],
            }
            for r in result_rows
        ],
    }


@router.post("/runs/trigger")
async def trigger_evaluation_run(
    x_scheduler_token: str | None = Header(default=None),
    max_cases: int = Query(20, ge=1, le=100),
):
    """
    Trigger a bounded baseline-vs-candidate evaluation run over promoted,
    replay-ready cases.

    Protected by the scheduler token (same as routes/scheduled.py) because
    this consumes real LLM budget, unlike the read endpoints above. This is
    intentionally NOT wired into pull-request CI — see Task 7's separation
    of deterministic CI tests from this LLM-bound trigger.
    """
    expected_token = settings.scheduler_secret_token
    if not expected_token:
        raise HTTPException(status_code=503, detail="Scheduler token is not configured")
    if not x_scheduler_token or not compare_digest(x_scheduler_token, expected_token):
        raise HTTPException(status_code=401, detail="Unauthorized scheduler request")

    from src.eval_flywheel.runner import run_bounded_evaluation

    result = await run_bounded_evaluation(max_cases=max_cases)
    return result


def _case_row_to_dict(row) -> dict:
    reasons = row["promotion_reasons"]
    if isinstance(reasons, str):
        import json

        try:
            reasons = json.loads(reasons)
        except (ValueError, TypeError):
            reasons = []
    return {
        "id": str(row["id"]),
        "prediction_id": str(row["prediction_id"]),
        "analysis_id": str(row["analysis_id"]) if row["analysis_id"] else None,
        "ticker": row["ticker"],
        "state": row["state"],
        "promotion_reasons": reasons or [],
        "capture_status": row["capture_status"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def _run_row_to_dict(row) -> dict:
    scores = row["aggregate_scores"]
    if isinstance(scores, str):
        import json

        try:
            scores = json.loads(scores)
        except (ValueError, TypeError):
            scores = {}
    return {
        "id": str(row["id"]),
        "candidate_config": row["candidate_config"],
        "corpus_version": row["corpus_version"],
        "case_count": row["case_count"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "status": row["status"],
        "decision": row["decision"],
        "aggregate_scores": scores or {},
        "budget_tokens_used": row["budget_tokens_used"],
        "budget_llm_calls": row["budget_llm_calls"],
    }
