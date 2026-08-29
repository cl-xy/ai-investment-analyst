"""
Query helpers that assemble `ResolvedPredictionFacts` from real production
tables. Kept separate from policy.py so the pure classification function
never touches the database (policy.py stays trivially unit-testable).

Data availability note: `citation_invalid_ratio` and `data_gaps_count` are
only derivable for predictions recorded via the streaming path, because only
that path stores `correlation_id` and calls `persist_citation_validation`.
Predictions from the non-streaming `/api/analyze` path (correlation_id IS
NULL) will have `citation_invalid_ratio=None` and `data_gaps_count=0` —
they remain eligible for promotion via the outcome-based reasons only.
"""

from __future__ import annotations

import json
from typing import Any

from src.db import fetch, fetchrow
from src.eval_flywheel.policy import ResolvedPredictionFacts

# Batch size for a single promotion sweep. Kept small and bounded like the
# existing resolve_predictions() LIMIT 50, to avoid unbounded work in one
# request/scheduled invocation.
DEFAULT_PROMOTION_BATCH_SIZE = 50


async def fetch_unclassified_resolved_predictions(
    limit: int = DEFAULT_PROMOTION_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """Resolved predictions that do not yet have an evaluation_cases row.

    Ordered oldest-first for stable, deterministic batch processing.
    """
    rows = await fetch(
        """
        SELECT p.id, p.analysis_id, p.ticker, p.signal, p.confidence,
               p.outcome, p.realized_return, p.excess_return, p.correlation_id
        FROM predictions p
        LEFT JOIN evaluation_cases ec ON ec.prediction_id = p.id
        WHERE p.resolved_at IS NOT NULL
          AND p.outcome IS NOT NULL
          AND ec.id IS NULL
        ORDER BY p.created_at ASC, p.id ASC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


async def _citation_invalid_ratio(correlation_id: str | None) -> float | None:
    """Derive the invalid-citation ratio for a run from citation_validations.

    Returns None (not zero) when there is no data to assess, so the policy
    can distinguish "known clean" from "unknown" rather than treating unknown
    coverage as automatically material or automatically clean.
    """
    if not correlation_id:
        return None
    row = await fetchrow(
        "SELECT validation_data FROM citation_validations WHERE run_id = $1",
        correlation_id,
    )
    if not row or not row["validation_data"]:
        return None
    data = row["validation_data"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return None
    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        return None
    total = len(results)
    if total == 0:
        return None
    invalid = sum(1 for r in results if not r.get("resolved", False))
    return invalid / total


async def _data_gaps_count(correlation_id: str | None) -> int:
    """Approximate coverage degradation for a run.

    evidence_artifacts only records what WAS retrieved, not what was
    missing, so absence of the full 7-source set for this run's tickers is
    used as a proxy: fewer than the expected artifact count is treated as a
    gap. This is intentionally conservative (best-effort signal), not a
    precise reconstruction of fetch_data_node's gap list.
    """
    if not correlation_id:
        return 0
    count = await fetch(
        "SELECT DISTINCT tool FROM evidence_artifacts WHERE run_id = $1",
        correlation_id,
    )
    expected_tools = 7  # matches fetch_data.py's fixed set of 7 tool calls
    observed = len(count)
    if observed == 0:
        # No artifacts recorded at all for this run is itself ambiguous
        # (could be an old pre-ledger run) — treat as unknown, not a gap.
        return 0
    return max(0, expected_tools - observed)


async def build_facts_for_prediction(row: dict[str, Any]) -> ResolvedPredictionFacts:
    """Assemble ResolvedPredictionFacts for one resolved prediction row."""
    correlation_id = row.get("correlation_id")
    citation_ratio, gaps = (
        await _citation_invalid_ratio(correlation_id),
        await _data_gaps_count(correlation_id),
    )
    return ResolvedPredictionFacts(
        prediction_id=str(row["id"]),
        ticker=row["ticker"],
        signal=row["signal"],
        confidence=row["confidence"],
        outcome=row["outcome"] or "neutral",
        realized_return=row.get("realized_return"),
        excess_return=row.get("excess_return"),
        citation_invalid_ratio=citation_ratio,
        data_gaps_count=gaps,
    )
