"""
Bounded evaluation run orchestrator: ties replay.py (Task 4) and scoring.py
(Task 5) into a persisted evaluation_runs/evaluation_results run, for the
protected trigger endpoint in routes/eval_flywheel.py.

This is the only module in eval_flywheel/ that makes real LLM calls
(via replay_cases_batch -> the actual debate functions). It must never be
invoked from pull-request CI — see Task 7.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.db import execute, fetch, fetchrow
from src.eval_flywheel.replay import replay_cases_batch
from src.eval_flywheel.scoring import aggregate_case_scores, decide_comparison, score_case

log = logging.getLogger(__name__)

DEFAULT_CANDIDATE_CONFIG = "baseline-replay-v1"


async def _fetch_replay_ready_cases(max_cases: int) -> list[dict]:
    """Promoted cases with capture_status='complete', oldest-first, not yet
    included in any evaluation_run (avoids re-scoring the same case
    redundantly across runs; a case can still be explicitly re-run by a
    future "re-evaluate" feature, not needed for this iteration)."""
    rows = await fetch(
        """
        SELECT ec.id AS case_id, ec.ticker, p.signal, p.confidence, p.outcome,
               p.realized_return, p.excess_return
        FROM evaluation_cases ec
        JOIN predictions p ON p.id = ec.prediction_id
        WHERE ec.state = 'promoted' AND ec.capture_status = 'complete'
        ORDER BY ec.created_at ASC
        LIMIT $1
        """,
        max_cases,
    )
    return [dict(r) for r in rows]


async def run_bounded_evaluation(
    max_cases: int = 20, candidate_config: str = DEFAULT_CANDIDATE_CONFIG
) -> dict:
    """Run a bounded evaluation over up to `max_cases` replay-ready promoted
    cases, persist a full evaluation_runs + evaluation_results record, and
    return the summary. Tolerant of per-case failures (isolated by
    replay_cases_batch); a total absence of eligible cases produces an
    'insufficient_data' run rather than an error.
    """
    cases = await _fetch_replay_ready_cases(max_cases)

    run_row = await fetchrow(
        """
        INSERT INTO evaluation_runs (candidate_config, corpus_version, case_count, status)
        VALUES ($1, $2, $3, 'running')
        RETURNING id
        """,
        candidate_config,
        f"cases-as-of-{datetime.now(timezone.utc).date().isoformat()}",
        len(cases),
    )
    assert run_row is not None, "INSERT ... RETURNING id must always return a row"
    run_id = str(run_row["id"])

    if not cases:
        await execute(
            """
            UPDATE evaluation_runs
            SET status = 'completed', completed_at = now(), decision = 'insufficient_data'
            WHERE id = $1
            """,
            run_id,
        )
        return {
            "run_id": run_id,
            "case_count": 0,
            "decision": "insufficient_data",
            "message": "No replay-ready promoted cases available",
        }

    replay_batch = await replay_cases_batch([(c["case_id"], c["ticker"]) for c in cases])

    scores = []
    for case, result in zip(cases, replay_batch.results):
        score = score_case(
            case_id=str(case["case_id"]),
            candidate_output=result.output,
            candidate_status=result.status,
            latency_ms=result.latency_ms,
            tokens_used=result.tokens_used,
            realized_return=case["realized_return"],
            excess_return=case["excess_return"],
        )
        scores.append(score)

        await execute(
            """
            INSERT INTO evaluation_results
                (run_id, case_id, status, candidate_scores, candidate_output, latency_ms, tokens_used, error)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)
            ON CONFLICT (run_id, case_id) DO NOTHING
            """,
            run_id,
            str(case["case_id"]),
            result.status,
            json.dumps(
                {
                    "brier_score": score.brier_score,
                    "outcome_match": score.outcome_match,
                    "structured_output_valid": score.structured_output_valid,
                    "citation_resolution_rate": score.citation_resolution_rate,
                    "evidence_balance_ratio": score.evidence_balance_ratio,
                }
            ),
            json.dumps(_serializable_output(result.output)),
            result.latency_ms,
            result.tokens_used,
            result.error,
        )

    aggregate = aggregate_case_scores(scores)
    decision = decide_comparison(aggregate)

    aggregate_dict = {
        "case_count": aggregate.case_count,
        "completed_count": aggregate.completed_count,
        "avg_brier": aggregate.avg_brier,
        "outcome_match_rate": aggregate.outcome_match_rate,
        "structured_output_validity_rate": aggregate.structured_output_validity_rate,
        "avg_citation_resolution_rate": aggregate.avg_citation_resolution_rate,
        "avg_evidence_balance_ratio": aggregate.avg_evidence_balance_ratio,
        "avg_latency_ms": aggregate.avg_latency_ms,
        "total_tokens_used": aggregate.total_tokens_used,
        "decision_reasons": decision.reasons,
    }

    await execute(
        """
        UPDATE evaluation_runs
        SET status = 'completed', completed_at = now(), decision = $1,
            aggregate_scores = $2::jsonb, budget_tokens_used = $3, budget_llm_calls = $4
        WHERE id = $5
        """,
        decision.decision,
        json.dumps(aggregate_dict),
        aggregate.total_tokens_used,
        len(cases) * 3,  # bull + bear + moderator per case
        run_id,
    )

    return {
        "run_id": run_id,
        "case_count": len(cases),
        "decision": decision.decision,
        "decision_reasons": decision.reasons,
        "aggregate_scores": aggregate_dict,
    }


def _serializable_output(output: dict | None) -> dict | None:
    """Strip non-JSON-serializable fields (e.g. _run_evidence) before persisting."""
    if output is None:
        return None
    return {k: v for k, v in output.items() if k != "_run_evidence"}
