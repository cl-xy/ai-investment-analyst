"""
Deterministic (zero-LLM) promotion policy.

Classifies a *resolved* prediction into a promotion decision for the
evaluation corpus. This is pure and side-effect free: no DB calls, no LLM
calls, no I/O. Callers (promotion.py) are responsible for persistence.

Design intent: a wrong prediction is noisy financial evidence, not proof of
a reasoning defect. Promotion targets *material* cases only:
  - high-confidence signal that was incorrect
  - a large benchmark-relative (excess-return) miss, even if not "incorrect"
  - unresolved/invalid citations at analysis time
  - degraded source coverage (data gaps) at analysis time

Every decision carries an explicit, human-readable reason list so promotion
is auditable rather than a black box.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal

PromotionState = Literal["candidate", "excluded"]

# --- Policy thresholds (documented, single source of truth) ---------------

# A high-confidence incorrect prediction is always material.
HIGH_CONFIDENCE_INCORRECT_CONFIDENCES: tuple[str, ...] = ("high",)

# A benchmark-relative (excess) return miss beyond this magnitude is material
# even when the discrete outcome label is "neutral" (e.g. a "buy" that
# underperformed the benchmark by a lot but didn't cross the incorrect
# threshold used in calibration.py's tighter neutral band).
MATERIAL_EXCESS_RETURN_MISS = 0.08  # 8 percentage points of benchmark-relative miss

# Citation invalidity ratio (unresolved / total) at or above this is material.
MATERIAL_CITATION_INVALID_RATIO = 0.34

# Any non-empty data_gaps list at analysis time is considered a coverage
# degradation worth promoting, since it means the original decision was made
# on incomplete information.
MATERIAL_DATA_GAPS_MIN_COUNT = 1


@dataclass(frozen=True, slots=True)
class ResolvedPredictionFacts:
    """Minimal, explicit input the policy needs. Deliberately excludes any
    field not required for classification, to keep the policy auditable and
    prevent accidental hindsight leakage into later replay code that might
    reuse this dataclass."""

    prediction_id: str
    ticker: str
    signal: str
    confidence: str
    outcome: str  # 'correct' | 'incorrect' | 'neutral'
    realized_return: float | None
    excess_return: float | None
    citation_invalid_ratio: float | None  # None if no citations were recorded
    data_gaps_count: int


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    state: PromotionState
    reasons: list[str] = field(default_factory=list)

    @property
    def is_promotable(self) -> bool:
        return self.state == "candidate"


def classify_prediction_for_promotion(facts: ResolvedPredictionFacts) -> PromotionDecision:
    """Pure classification function. No I/O, no LLM calls, no randomness.

    Same input always produces the same output — required for idempotent,
    auditable promotion and for deterministic CI tests.
    """
    reasons: list[str] = []

    if facts.outcome == "incorrect" and facts.confidence in HIGH_CONFIDENCE_INCORRECT_CONFIDENCES:
        reasons.append(
            f"high_confidence_incorrect: confidence={facts.confidence} outcome={facts.outcome}"
        )

    if facts.excess_return is not None and abs(facts.excess_return) >= MATERIAL_EXCESS_RETURN_MISS:
        # Only material if the miss is in the "wrong direction" for the signal,
        # i.e. an unfavorable excess return, not simply high volatility.
        unfavorable = (
            (facts.signal == "buy" and facts.excess_return < 0)
            or (facts.signal == "sell" and facts.excess_return > 0)
            or (facts.signal == "hold" and abs(facts.excess_return) >= MATERIAL_EXCESS_RETURN_MISS)
        )
        if unfavorable:
            reasons.append(
                f"material_excess_return_miss: excess_return={facts.excess_return:.4f} "
                f"signal={facts.signal}"
            )

    if (
        facts.citation_invalid_ratio is not None
        and facts.citation_invalid_ratio >= MATERIAL_CITATION_INVALID_RATIO
    ):
        reasons.append(f"unresolved_citations: invalid_ratio={facts.citation_invalid_ratio:.2f}")

    if facts.data_gaps_count >= MATERIAL_DATA_GAPS_MIN_COUNT:
        reasons.append(f"degraded_source_coverage: data_gaps_count={facts.data_gaps_count}")

    if reasons:
        return PromotionDecision(state="candidate", reasons=reasons)
    return PromotionDecision(state="excluded", reasons=["no_material_signal"])


def compute_case_hash(prediction_id: str, reasons: list[str]) -> str:
    """Deterministic dedup key for a promotion decision.

    Keyed on prediction_id + sorted reasons, so re-running promotion against
    the same resolved prediction with the same facts always yields the same
    hash (idempotent promotion), while a policy change that adds/removes a
    reason produces a new hash (intentional: re-evaluates under new policy).
    """
    canonical = prediction_id + "|" + "|".join(sorted(reasons))
    return hashlib.sha256(canonical.encode()).hexdigest()


def facts_from_prediction_row(row: dict[str, Any]) -> ResolvedPredictionFacts:
    """Build ResolvedPredictionFacts from a `predictions` row plus optional
    citation-validation aggregates. Row must already be resolved
    (resolved_at IS NOT NULL) — callers are responsible for that filter.
    """
    return ResolvedPredictionFacts(
        prediction_id=str(row["id"]),
        ticker=row["ticker"],
        signal=row["signal"],
        confidence=row["confidence"],
        outcome=row["outcome"] or "neutral",
        realized_return=row.get("realized_return"),
        excess_return=row.get("excess_return"),
        citation_invalid_ratio=row.get("citation_invalid_ratio"),
        data_gaps_count=row.get("data_gaps_count") or 0,
    )
