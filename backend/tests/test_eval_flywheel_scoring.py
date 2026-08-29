"""
Tests for Task 5: outcome/quality scoring and guarded comparison policy.
"""

from src.eval_flywheel.scoring import (
    MIN_CASES_FOR_DECISION,
    MIN_CITATION_RESOLUTION_RATE,
    MIN_STRUCTURED_OUTPUT_VALIDITY,
    AggregateScores,
    CaseScore,
    aggregate_case_scores,
    decide_comparison,
    score_case,
)
from src.evidence.registry import RunEvidence


class TestScoreCaseFailedOrIncomplete:
    def test_non_completed_status_returns_null_scores(self):
        score = score_case(
            case_id="c1",
            candidate_output=None,
            candidate_status="timeout",
            latency_ms=500,
        )
        assert score.outcome_match is None
        assert score.structured_output_valid is False
        assert score.brier_score is None


class TestScoreCaseOutcomeMatch:
    def test_buy_signal_correct_against_positive_excess_return(self):
        score = score_case(
            case_id="c1",
            candidate_output={"signal": "buy", "confidence": "high", "thesis": "t"},
            candidate_status="completed",
            latency_ms=1000,
            excess_return=0.05,
        )
        assert score.outcome_match is True
        assert score.brier_score is not None
        assert score.brier_score < 0.1  # high confidence + correct = low Brier

    def test_buy_signal_incorrect_against_negative_excess_return(self):
        score = score_case(
            case_id="c1",
            candidate_output={"signal": "buy", "confidence": "high", "thesis": "t"},
            candidate_status="completed",
            latency_ms=1000,
            excess_return=-0.05,
        )
        assert score.outcome_match is False
        assert score.brier_score is not None
        assert score.brier_score > 0.5  # high confidence + wrong = high Brier

    def test_missing_return_data_leaves_outcome_match_none(self):
        score = score_case(
            case_id="c1",
            candidate_output={"signal": "buy", "confidence": "high", "thesis": "t"},
            candidate_status="completed",
            latency_ms=1000,
        )
        assert score.outcome_match is None
        assert score.brier_score is None

    def test_insufficient_data_signal_never_scored(self):
        score = score_case(
            case_id="c1",
            candidate_output={"signal": "insufficient_data", "confidence": "low", "thesis": ""},
            candidate_status="completed",
            latency_ms=1000,
            excess_return=0.05,
        )
        assert score.outcome_match is None
        assert score.structured_output_valid is False


class TestScoreCaseStructuredValidity:
    def test_missing_thesis_marks_invalid(self):
        score = score_case(
            case_id="c1",
            candidate_output={"signal": "buy", "confidence": "high", "thesis": ""},
            candidate_status="completed",
            latency_ms=100,
        )
        assert score.structured_output_valid is False

    def test_present_signal_and_thesis_marks_valid(self):
        score = score_case(
            case_id="c1",
            candidate_output={"signal": "buy", "confidence": "high", "thesis": "t"},
            candidate_status="completed",
            latency_ms=100,
        )
        assert score.structured_output_valid is True


class TestScoreCaseCitationReuse:
    def test_reuses_validate_citations_against_real_run_evidence(self):
        run_evidence = RunEvidence(run_id="replay-1")
        artifact = run_evidence.register("yfinance", "get_quote", "NVDA", {"price": 1})
        score = score_case(
            case_id="c1",
            candidate_output={
                "signal": "buy",
                "confidence": "high",
                "thesis": "t",
                "citations": [
                    {"source_id": artifact.artifact_id, "claim": "x", "provider": "yfinance"},
                    {"source_id": "ev_nonexistent", "claim": "y", "provider": "yfinance"},
                ],
                "_run_evidence": run_evidence,
            },
            candidate_status="completed",
            latency_ms=100,
        )
        assert score.citation_resolution_rate == 0.5

    def test_falls_back_to_well_formedness_without_run_evidence(self):
        score = score_case(
            case_id="c1",
            candidate_output={
                "signal": "buy",
                "confidence": "high",
                "thesis": "t",
                "citations": [
                    {"source_id": "ev_abc", "claim": "x"},
                    {"source_id": "", "claim": "y"},
                ],
            },
            candidate_status="completed",
            latency_ms=100,
        )
        assert score.citation_resolution_rate == 0.5

    def test_no_citations_leaves_rate_none(self):
        score = score_case(
            case_id="c1",
            candidate_output={"signal": "buy", "confidence": "high", "thesis": "t"},
            candidate_status="completed",
            latency_ms=100,
        )
        assert score.citation_resolution_rate is None


class TestScoreCaseEvidenceBalance:
    def test_balanced_evidence_ratio_is_one(self):
        score = score_case(
            case_id="c1",
            candidate_output={
                "signal": "buy",
                "confidence": "high",
                "thesis": "t",
                "_bull_evidence_count": 3,
                "_bear_evidence_count": 3,
            },
            candidate_status="completed",
            latency_ms=100,
        )
        assert score.evidence_balance_ratio == 1.0

    def test_imbalanced_evidence_ratio_below_one(self):
        score = score_case(
            case_id="c1",
            candidate_output={
                "signal": "buy",
                "confidence": "high",
                "thesis": "t",
                "_bull_evidence_count": 4,
                "_bear_evidence_count": 1,
            },
            candidate_status="completed",
            latency_ms=100,
        )
        assert score.evidence_balance_ratio == 0.25


class TestAggregateCaseScores:
    def test_empty_scores_returns_zeroed_aggregate(self):
        agg = aggregate_case_scores([])
        assert agg.case_count == 0
        assert agg.structured_output_validity_rate == 0.0

    def test_partial_and_failed_cases_counted_but_do_not_pollute_metric_averages(self):
        scores = [
            CaseScore(
                case_id="c1",
                brier_score=0.1,
                outcome_match=True,
                structured_output_valid=True,
                citation_resolution_rate=1.0,
                bull_evidence_count=3,
                bear_evidence_count=3,
                evidence_balance_ratio=1.0,
                latency_ms=1000,
                tokens_used=500,
            ),
            # Failed case: contributes to case_count/latency but not to
            # brier/outcome/citation averages since those are None.
            CaseScore(
                case_id="c2",
                brier_score=None,
                outcome_match=None,
                structured_output_valid=False,
                citation_resolution_rate=None,
                bull_evidence_count=0,
                bear_evidence_count=0,
                evidence_balance_ratio=None,
                latency_ms=200,
                tokens_used=0,
            ),
        ]
        agg = aggregate_case_scores(scores)
        assert agg.case_count == 2
        assert agg.avg_brier == 0.1  # only c1 contributes
        assert agg.outcome_match_rate == 1.0
        assert agg.structured_output_validity_rate == 0.5  # 1 of 2
        assert agg.avg_latency_ms == 600  # (1000+200)/2, includes failed case
        assert agg.total_tokens_used == 500


class TestDecideComparisonInsufficientSample:
    def test_below_minimum_always_insufficient_data_regardless_of_quality(self):
        agg = AggregateScores(
            case_count=5,
            completed_count=MIN_CASES_FOR_DECISION - 1,
            avg_brier=0.0,
            outcome_match_rate=1.0,
            structured_output_validity_rate=1.0,
            avg_citation_resolution_rate=1.0,
            avg_evidence_balance_ratio=1.0,
            avg_latency_ms=100,
            total_tokens_used=100,
        )
        decision = decide_comparison(agg)
        assert decision.decision == "insufficient_data"

    def test_at_minimum_proceeds_to_real_evaluation(self):
        agg = AggregateScores(
            case_count=MIN_CASES_FOR_DECISION,
            completed_count=MIN_CASES_FOR_DECISION,
            avg_brier=0.0,
            outcome_match_rate=1.0,
            structured_output_validity_rate=1.0,
            avg_citation_resolution_rate=1.0,
            avg_evidence_balance_ratio=1.0,
            avg_latency_ms=100,
            total_tokens_used=100,
        )
        decision = decide_comparison(agg)
        assert decision.decision == "pass"


class TestDecideComparisonReject:
    def _good_agg(self, **overrides) -> AggregateScores:
        defaults = dict(
            case_count=MIN_CASES_FOR_DECISION,
            completed_count=MIN_CASES_FOR_DECISION,
            avg_brier=0.05,
            outcome_match_rate=0.9,
            structured_output_validity_rate=1.0,
            avg_citation_resolution_rate=1.0,
            avg_evidence_balance_ratio=1.0,
            avg_latency_ms=1000,
            total_tokens_used=1000,
        )
        defaults.update(overrides)
        return AggregateScores(**defaults)

    def test_low_structured_validity_rejects_even_with_good_outcome(self):
        agg = self._good_agg(
            structured_output_validity_rate=MIN_STRUCTURED_OUTPUT_VALIDITY - 0.1,
            outcome_match_rate=1.0,
            avg_brier=0.0,
        )
        decision = decide_comparison(agg)
        assert decision.decision == "reject"
        assert any("structured_output_validity_rate" in r for r in decision.reasons)

    def test_low_citation_resolution_rejects(self):
        agg = self._good_agg(
            avg_citation_resolution_rate=MIN_CITATION_RESOLUTION_RATE - 0.1,
        )
        decision = decide_comparison(agg)
        assert decision.decision == "reject"
        assert any("citation_resolution_rate" in r for r in decision.reasons)

    def test_latency_regression_beyond_ratio_rejects(self):
        baseline = self._good_agg(avg_latency_ms=1000)
        candidate = self._good_agg(avg_latency_ms=2000)  # exactly 2x baseline
        decision = decide_comparison(candidate, baseline)
        assert decision.decision == "reject"
        assert any("avg_latency_ms" in r for r in decision.reasons)

    def test_pass_cannot_happen_on_outcome_score_alone(self):
        """Even a perfect outcome/brier score must reject if reliability
        floors are violated — outcome alone is never sufficient."""
        agg = self._good_agg(
            outcome_match_rate=1.0,
            avg_brier=0.0,
            structured_output_validity_rate=0.5,  # badly below floor
        )
        decision = decide_comparison(agg)
        assert decision.decision == "reject"


class TestDecideComparisonInvestigate:
    def _good_agg(self, **overrides) -> AggregateScores:
        defaults = dict(
            case_count=MIN_CASES_FOR_DECISION,
            completed_count=MIN_CASES_FOR_DECISION,
            avg_brier=0.05,
            outcome_match_rate=0.9,
            structured_output_validity_rate=1.0,
            avg_citation_resolution_rate=1.0,
            avg_evidence_balance_ratio=1.0,
            avg_latency_ms=1000,
            total_tokens_used=1000,
        )
        defaults.update(overrides)
        return AggregateScores(**defaults)

    def test_poor_outcome_match_rate_investigates(self):
        agg = self._good_agg(outcome_match_rate=0.3)
        decision = decide_comparison(agg)
        assert decision.decision == "investigate"

    def test_worse_brier_than_baseline_investigates(self):
        baseline = self._good_agg(avg_brier=0.05)
        candidate = self._good_agg(avg_brier=0.20, outcome_match_rate=0.9)
        decision = decide_comparison(candidate, baseline)
        assert decision.decision == "investigate"


class TestDecideComparisonPass:
    def test_clean_pass_with_no_baseline(self):
        agg = AggregateScores(
            case_count=MIN_CASES_FOR_DECISION,
            completed_count=MIN_CASES_FOR_DECISION,
            avg_brier=0.05,
            outcome_match_rate=0.9,
            structured_output_validity_rate=1.0,
            avg_citation_resolution_rate=1.0,
            avg_evidence_balance_ratio=1.0,
            avg_latency_ms=1000,
            total_tokens_used=1000,
        )
        decision = decide_comparison(agg)
        assert decision.decision == "pass"
