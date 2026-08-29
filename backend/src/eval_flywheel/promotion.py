"""
Promotion orchestration: wires the deterministic policy (policy.py) and
full-payload linkage (capture.py) into the existing prediction-resolution
flow. Designed to be called from calibration.py's resolve_predictions()
after a batch of predictions has been resolved and committed.

Failure isolation: a failure anywhere in this module must never affect
prediction resolution, which is the pre-existing, higher-value contract.
Callers should wrap invocations in a try/except and log, matching the
tolerant-degradation style already used in pipeline.py and debate.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.db import execute, fetchrow
from src.eval_flywheel.capture import capture_case_artifacts
from src.eval_flywheel.policy import classify_prediction_for_promotion, compute_case_hash
from src.eval_flywheel.queries import build_facts_for_prediction

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PromotionBatchSummary:
    considered: int = 0
    promoted: int = 0
    excluded: int = 0
    already_classified: int = 0
    failed: int = 0


async def promote_resolved_prediction(row: dict) -> str:
    """Classify and (if eligible) promote a single resolved prediction row.

    Idempotent: relies on the UNIQUE index on evaluation_cases.prediction_id
    (added in Task 1's migration) to make a duplicate insert attempt a
    no-op rather than a duplicate case. Returns one of:
    "promoted", "excluded", "already_classified", "failed".

    Never raises for expected conditions (already classified, capture
    failure) — only truly unexpected errors propagate, and even those are
    caught by the caller in resolve_predictions().
    """
    prediction_id = str(row["id"])

    existing = await fetchrow(
        "SELECT id FROM evaluation_cases WHERE prediction_id = $1", prediction_id
    )
    if existing:
        return "already_classified"

    facts = await build_facts_for_prediction(row)
    decision = classify_prediction_for_promotion(facts)
    case_hash = compute_case_hash(prediction_id, decision.reasons)

    if decision.state == "excluded":
        # Still record the exclusion for audit/dedup — re-running promotion
        # on the same prediction (e.g. after a retry) must not reclassify it.
        # ON CONFLICT targets prediction_id (checked above) since that's the
        # actual dedup key for "has this prediction been classified yet";
        # case_hash's own unique index exists for cross-prediction dedup of
        # identical reason sets and is not expected to collide here.
        await execute(
            """
            INSERT INTO evaluation_cases
                (prediction_id, analysis_id, ticker, case_hash, state, promotion_reasons, capture_status)
            VALUES ($1, $2, $3, $4, 'excluded', $5::jsonb, 'failed')
            ON CONFLICT (prediction_id) DO NOTHING
            """,
            prediction_id,
            row.get("analysis_id"),
            row["ticker"],
            case_hash,
            _to_jsonb(decision.reasons),
        )
        return "excluded"

    case_row = await fetchrow(
        """
        INSERT INTO evaluation_cases
            (prediction_id, analysis_id, ticker, case_hash, state, promotion_reasons, capture_status)
        VALUES ($1, $2, $3, $4, 'promoted', $5::jsonb, 'pending')
        ON CONFLICT (prediction_id) DO NOTHING
        RETURNING id
        """,
        prediction_id,
        row.get("analysis_id"),
        row["ticker"],
        case_hash,
        _to_jsonb(decision.reasons),
    )
    if not case_row:
        # Lost a race with a concurrent promotion sweep — already handled.
        return "already_classified"

    case_id = str(case_row["id"])
    try:
        await capture_case_artifacts(case_id, row.get("correlation_id"))
    except Exception:
        log.warning("eval_case_capture_failed case_id=%s", case_id, exc_info=True)
        # Case remains promoted with capture_status left at whatever
        # capture_case_artifacts managed to set (or 'pending' if it raised
        # before updating) — never rolled back, since the case itself is
        # still a valid, auditable record even without replay capability.

    return "promoted"


def _to_jsonb(reasons: list[str]) -> str:
    import json

    return json.dumps(reasons)


async def promote_resolved_predictions_batch(rows: list[dict]) -> PromotionBatchSummary:
    """Run promotion over a batch of already-resolved prediction rows.

    Each row is handled independently; one failure does not abort the batch.
    """
    promoted = excluded = already = failed = 0
    for row in rows:
        try:
            outcome = await promote_resolved_prediction(row)
        except Exception:
            log.warning("eval_case_promotion_failed prediction_id=%s", row.get("id"), exc_info=True)
            failed += 1
            continue
        if outcome == "promoted":
            promoted += 1
        elif outcome == "excluded":
            excluded += 1
        else:
            already += 1

    return PromotionBatchSummary(
        considered=len(rows),
        promoted=promoted,
        excluded=excluded,
        already_classified=already,
        failed=failed,
    )
