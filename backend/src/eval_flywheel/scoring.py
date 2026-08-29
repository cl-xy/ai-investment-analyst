"""
Outcome/quality scoring and guarded baseline-vs-candidate comparison policy
(Task 5).

Scope note: scores here are computed against what Task 4 actually replays
(the debate reasoning core). This intentionally does NOT include
cache-hit-rate or tool-success-rate — those are properties of
fetch_data_node, which replay bypasses entirely (see replay.py's module
docstring).

Hindsight-leakage boundary: the resolved outcome (predictions.outcome /
realized_return / excess_return) is read HERE, and only here, to score the
already-generated candidate output. It is never passed into replay.py's
inputs — see replay.py and _reconstruct_state's hard assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.api.routes.calibration import _determine_outcome
from src.evidence.registry import RunEvidence, validate_citations

Decision = Literal["pass", "investigate", "reject", "insufficient_data"]

# A comparison run needs at least this many completed (non-error/timeout)
# cases before any pass/reject conclusion is trusted. Below this, the
# decision is always "insufficient_data" regardless of how good the
# aggregate scores look — small samples are not evidence.
MIN_CASES_FOR_DECISION = 10

# Confidence-to-probability mapping, matching calibration.py's convention
# exactly (kept as a local constant rather than importing calibration.py's
# module-level dict, since it isn't exported as a shared name there).
_CONFIDENCE_TO_PROB = {"high": 0.80, "medium": 0.55, "low": 0.30}

# Hard reliability floors: a candidate cannot "pass" purely on a good
# outcome score if it degrades these, since a lucky outcome on noisy
# financial data does not indicate durable model/prompt quality.
MIN_STRUCTURED_OUTPUT_VALIDITY = 0.95
MIN_CITATION_RESOLUTION_RATE = 0.70
MAX_LATENCY_REGRESSION_RATIO = 1.5  # candidate must not be >50% slower


@dataclass(frozen=True, slots=True)
class CaseScore:
    case_id: str
    brier_score: float | None
    outcome_match: (
        bool | None
    )  # did candidate's signal direction match baseline's realized outcome?
    structured_output_valid: bool
    citation_resolution_rate: float | None
    bull_evidence_count: int
    bear_evidence_count: int
    evidence_balance_ratio: float | None  # min(bull,bear)/max(bull,bear), 1.0 = perfectly balanced
    latency_ms: int
    tokens_used: int


def score_case(
    *,
    case_id: str,
    candidate_output: dict[str, Any] | None,
    candidate_status: str,
    latency_ms: int,
    tokens_used: int = 0,
    realized_return: float | None = None,
    excess_return: float | None = None,
) -> CaseScore:
    """Score one replayed case's candidate output against its known outcome.

    `realized_return`/`excess_return` come from the ORIGINAL prediction's
    resolution (predictions table) — used only to grade the candidate's
    output after the fact, never fed into replay (see replay.py's
    hindsight-leakage guarantee).
    """
    if candidate_status != "completed" or candidate_output is None:
        return CaseScore(
            case_id=case_id,
            brier_score=None,
            outcome_match=None,
            structured_output_valid=False,
            citation_resolution_rate=None,
            bull_evidence_count=0,
            bear_evidence_count=0,
            evidence_balance_ratio=None,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
        )

    candidate_signal = candidate_output.get("signal")
    candidate_confidence = candidate_output.get("confidence", "medium")

    structured_valid = bool(candidate_signal) and bool(candidate_output.get("thesis"))

    # Grade the CANDIDATE's own signal against the same realized outcome
    # that graded the original prediction, by directly reusing
    # _determine_outcome — the same function calibration.py's
    # resolve_predictions() uses. This is a genuine re-derivation (not a
    # label comparison against resolved_outcome), so a candidate that
    # produces a different signal than the original gets independently and
    # correctly graded against what actually happened.
    outcome_match: bool | None = None
    check_return = excess_return if excess_return is not None else realized_return
    if candidate_signal in ("buy", "hold", "sell") and check_return is not None:
        candidate_outcome = _determine_outcome(
            candidate_signal, check_return, is_excess=(excess_return is not None)
        )
        outcome_match = candidate_outcome == "correct"

    brier = None
    if candidate_signal in ("buy", "hold", "sell") and outcome_match is not None:
        prob = _CONFIDENCE_TO_PROB.get(candidate_confidence, 0.5)
        actual = 1.0 if outcome_match else 0.0
        brier = (prob - actual) ** 2

    citation_rate = None
    citations = candidate_output.get("citations") or []
    if citations:
        run_evidence = candidate_output.get("_run_evidence")
        if isinstance(run_evidence, RunEvidence):
            # Genuine reuse: validate against the actual artifact ledger this
            # replay run registered in _reconstruct_state.
            _results, confidence_multiplier = validate_citations(citations, run_evidence)
            resolved_count = sum(1 for r in _results if r.resolved)
            citation_rate = resolved_count / len(citations)
        else:
            # Fallback for cases where _run_evidence wasn't carried through
            # (e.g. candidate_output was rehydrated from persisted JSON,
            # which cannot serialize a RunEvidence object). Degrades to a
            # structural well-formedness check rather than failing outright.
            well_formed = sum(1 for c in citations if c.get("source_id"))
            citation_rate = well_formed / len(citations)

    bull_count = candidate_output.get("_bull_evidence_count", 0)
    bear_count = candidate_output.get("_bear_evidence_count", 0)
    balance_ratio = None
    if bull_count > 0 or bear_count > 0:
        balance_ratio = min(bull_count, bear_count) / max(bull_count, bear_count, 1)

    return CaseScore(
        case_id=case_id,
        brier_score=brier,
        outcome_match=outcome_match,
        structured_output_valid=structured_valid,
        citation_resolution_rate=citation_rate,
        bull_evidence_count=bull_count,
        bear_evidence_count=bear_count,
        evidence_balance_ratio=balance_ratio,
        latency_ms=latency_ms,
        tokens_used=tokens_used,
    )


@dataclass(frozen=True, slots=True)
class AggregateScores:
    case_count: int
    completed_count: int
    avg_brier: float | None
    outcome_match_rate: float | None
    structured_output_validity_rate: float
    avg_citation_resolution_rate: float | None
    avg_evidence_balance_ratio: float | None
    avg_latency_ms: float
    total_tokens_used: int


def aggregate_case_scores(scores: list[CaseScore]) -> AggregateScores:
    """Aggregate per-case scores. Tolerates partial/failed cases: only
    completed cases with a defined metric contribute to that metric's
    average, but ALL cases (including failed) count toward case_count and
    structured_output_validity_rate's denominator."""
    total = len(scores)
    completed = [s for s in scores if s.outcome_match is not None or s.structured_output_valid]

    briers = [s.brier_score for s in scores if s.brier_score is not None]
    matches = [s.outcome_match for s in scores if s.outcome_match is not None]
    citation_rates = [
        s.citation_resolution_rate for s in scores if s.citation_resolution_rate is not None
    ]
    balance_ratios = [
        s.evidence_balance_ratio for s in scores if s.evidence_balance_ratio is not None
    ]
    valid_count = sum(1 for s in scores if s.structured_output_valid)

    return AggregateScores(
        case_count=total,
        completed_count=len(completed),
        avg_brier=(sum(briers) / len(briers)) if briers else None,
        outcome_match_rate=(sum(1 for m in matches if m) / len(matches)) if matches else None,
        structured_output_validity_rate=(valid_count / total) if total else 0.0,
        avg_citation_resolution_rate=(
            sum(citation_rates) / len(citation_rates) if citation_rates else None
        ),
        avg_evidence_balance_ratio=(
            sum(balance_ratios) / len(balance_ratios) if balance_ratios else None
        ),
        avg_latency_ms=(sum(s.latency_ms for s in scores) / total) if total else 0.0,
        total_tokens_used=sum(s.tokens_used for s in scores),
    )


@dataclass(frozen=True, slots=True)
class ComparisonDecision:
    decision: Decision
    reasons: list[str] = field(default_factory=list)


def decide_comparison(
    candidate: AggregateScores,
    baseline: AggregateScores | None = None,
) -> ComparisonDecision:
    """Guarded pass/investigate/reject policy.

    A candidate can never "pass" on outcome score alone: it must also clear
    hard reliability floors (structured-output validity, citation
    resolution) and must not regress badly on cost/latency versus baseline,
    when a baseline is available. Below MIN_CASES_FOR_DECISION completed
    cases, the decision is always "insufficient_data".
    """
    if candidate.completed_count < MIN_CASES_FOR_DECISION:
        return ComparisonDecision(
            decision="insufficient_data",
            reasons=[
                f"only {candidate.completed_count} completed cases "
                f"(minimum {MIN_CASES_FOR_DECISION} required for a decision)"
            ],
        )

    reasons: list[str] = []
    reject = False

    if candidate.structured_output_validity_rate < MIN_STRUCTURED_OUTPUT_VALIDITY:
        reject = True
        reasons.append(
            f"structured_output_validity_rate={candidate.structured_output_validity_rate:.2f} "
            f"below floor {MIN_STRUCTURED_OUTPUT_VALIDITY}"
        )

    if (
        candidate.avg_citation_resolution_rate is not None
        and candidate.avg_citation_resolution_rate < MIN_CITATION_RESOLUTION_RATE
    ):
        reject = True
        reasons.append(
            f"avg_citation_resolution_rate={candidate.avg_citation_resolution_rate:.2f} "
            f"below floor {MIN_CITATION_RESOLUTION_RATE}"
        )

    if (
        baseline is not None
        and baseline.avg_latency_ms > 0
        and candidate.avg_latency_ms > baseline.avg_latency_ms * MAX_LATENCY_REGRESSION_RATIO
    ):
        reject = True
        reasons.append(
            f"avg_latency_ms={candidate.avg_latency_ms:.0f} exceeds "
            f"{MAX_LATENCY_REGRESSION_RATIO}x baseline ({baseline.avg_latency_ms:.0f})"
        )

    if reject:
        return ComparisonDecision(decision="reject", reasons=reasons)

    investigate = False
    if candidate.outcome_match_rate is not None and candidate.outcome_match_rate < 0.5:
        investigate = True
        reasons.append(f"outcome_match_rate={candidate.outcome_match_rate:.2f} below 0.5")

    if (
        baseline is not None
        and candidate.avg_brier is not None
        and baseline.avg_brier is not None
        and candidate.avg_brier > baseline.avg_brier
    ):
        investigate = True
        reasons.append(
            f"avg_brier={candidate.avg_brier:.3f} worse than baseline ({baseline.avg_brier:.3f})"
        )

    if investigate:
        return ComparisonDecision(decision="investigate", reasons=reasons)

    reasons.append("all reliability floors met; no outcome/cost regression detected")
    return ComparisonDecision(decision="pass", reasons=reasons)
