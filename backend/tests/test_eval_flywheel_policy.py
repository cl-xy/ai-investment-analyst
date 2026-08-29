"""
Unit tests for the deterministic (zero-LLM, zero-DB) promotion policy.

These tests exercise `classify_prediction_for_promotion` purely in memory —
no mocks needed since the function has no I/O.
"""

from src.eval_flywheel.policy import (
    MATERIAL_CITATION_INVALID_RATIO,
    MATERIAL_DATA_GAPS_MIN_COUNT,
    MATERIAL_EXCESS_RETURN_MISS,
    ResolvedPredictionFacts,
    classify_prediction_for_promotion,
    compute_case_hash,
    facts_from_prediction_row,
)


def _facts(**overrides) -> ResolvedPredictionFacts:
    defaults = dict(
        prediction_id="pred-1",
        ticker="NVDA",
        signal="buy",
        confidence="medium",
        outcome="correct",
        realized_return=0.05,
        excess_return=0.03,
        citation_invalid_ratio=None,
        data_gaps_count=0,
    )
    defaults.update(overrides)
    return ResolvedPredictionFacts(**defaults)


class TestNoMaterialSignal:
    def test_clean_correct_prediction_excluded(self):
        decision = classify_prediction_for_promotion(_facts())
        assert decision.state == "excluded"
        assert decision.reasons == ["no_material_signal"]
        assert decision.is_promotable is False


class TestHighConfidenceIncorrect:
    def test_high_confidence_incorrect_is_promoted(self):
        decision = classify_prediction_for_promotion(
            _facts(confidence="high", outcome="incorrect", excess_return=0.0)
        )
        assert decision.is_promotable
        assert any("high_confidence_incorrect" in r for r in decision.reasons)

    def test_medium_confidence_incorrect_not_promoted_on_this_reason_alone(self):
        decision = classify_prediction_for_promotion(
            _facts(confidence="medium", outcome="incorrect", excess_return=0.0)
        )
        assert not any("high_confidence_incorrect" in r for r in decision.reasons)

    def test_low_confidence_incorrect_not_promoted_on_this_reason_alone(self):
        decision = classify_prediction_for_promotion(
            _facts(confidence="low", outcome="incorrect", excess_return=0.0)
        )
        assert not any("high_confidence_incorrect" in r for r in decision.reasons)

    def test_high_confidence_correct_not_promoted_on_this_reason(self):
        decision = classify_prediction_for_promotion(
            _facts(confidence="high", outcome="correct", excess_return=0.0)
        )
        assert not any("high_confidence_incorrect" in r for r in decision.reasons)


class TestMaterialExcessReturnMiss:
    def test_buy_signal_unfavorable_miss_promoted(self):
        decision = classify_prediction_for_promotion(
            _facts(signal="buy", excess_return=-(MATERIAL_EXCESS_RETURN_MISS + 0.01))
        )
        assert decision.is_promotable
        assert any("material_excess_return_miss" in r for r in decision.reasons)

    def test_buy_signal_favorable_large_excess_not_promoted_on_this_reason(self):
        # A buy that massively outperformed is not a failure worth promoting.
        decision = classify_prediction_for_promotion(
            _facts(signal="buy", excess_return=MATERIAL_EXCESS_RETURN_MISS + 0.05)
        )
        assert not any("material_excess_return_miss" in r for r in decision.reasons)

    def test_sell_signal_unfavorable_miss_promoted(self):
        decision = classify_prediction_for_promotion(
            _facts(signal="sell", excess_return=MATERIAL_EXCESS_RETURN_MISS + 0.02)
        )
        assert decision.is_promotable
        assert any("material_excess_return_miss" in r for r in decision.reasons)

    def test_hold_signal_large_move_either_direction_promoted(self):
        decision = classify_prediction_for_promotion(
            _facts(signal="hold", excess_return=-(MATERIAL_EXCESS_RETURN_MISS + 0.01))
        )
        assert decision.is_promotable
        assert any("material_excess_return_miss" in r for r in decision.reasons)

    def test_below_threshold_not_material(self):
        decision = classify_prediction_for_promotion(
            _facts(signal="buy", excess_return=-(MATERIAL_EXCESS_RETURN_MISS - 0.001))
        )
        assert not any("material_excess_return_miss" in r for r in decision.reasons)

    def test_exact_threshold_boundary_is_material(self):
        decision = classify_prediction_for_promotion(
            _facts(signal="buy", excess_return=-MATERIAL_EXCESS_RETURN_MISS)
        )
        assert any("material_excess_return_miss" in r for r in decision.reasons)

    def test_none_excess_return_never_triggers_this_reason(self):
        decision = classify_prediction_for_promotion(_facts(excess_return=None))
        assert not any("material_excess_return_miss" in r for r in decision.reasons)


class TestUnresolvedCitations:
    def test_above_threshold_promoted(self):
        decision = classify_prediction_for_promotion(
            _facts(citation_invalid_ratio=MATERIAL_CITATION_INVALID_RATIO + 0.01)
        )
        assert decision.is_promotable
        assert any("unresolved_citations" in r for r in decision.reasons)

    def test_exact_threshold_boundary_is_material(self):
        decision = classify_prediction_for_promotion(
            _facts(citation_invalid_ratio=MATERIAL_CITATION_INVALID_RATIO)
        )
        assert any("unresolved_citations" in r for r in decision.reasons)

    def test_below_threshold_not_material(self):
        decision = classify_prediction_for_promotion(
            _facts(citation_invalid_ratio=MATERIAL_CITATION_INVALID_RATIO - 0.01)
        )
        assert not any("unresolved_citations" in r for r in decision.reasons)

    def test_none_ratio_never_triggers_this_reason(self):
        decision = classify_prediction_for_promotion(_facts(citation_invalid_ratio=None))
        assert not any("unresolved_citations" in r for r in decision.reasons)


class TestDegradedCoverage:
    def test_min_gap_count_promoted(self):
        decision = classify_prediction_for_promotion(
            _facts(data_gaps_count=MATERIAL_DATA_GAPS_MIN_COUNT)
        )
        assert decision.is_promotable
        assert any("degraded_source_coverage" in r for r in decision.reasons)

    def test_zero_gaps_not_material(self):
        decision = classify_prediction_for_promotion(_facts(data_gaps_count=0))
        assert not any("degraded_source_coverage" in r for r in decision.reasons)


class TestCombinedReasons:
    def test_multiple_reasons_all_recorded(self):
        decision = classify_prediction_for_promotion(
            _facts(
                confidence="high",
                outcome="incorrect",
                signal="buy",
                excess_return=-(MATERIAL_EXCESS_RETURN_MISS + 0.05),
                citation_invalid_ratio=MATERIAL_CITATION_INVALID_RATIO + 0.1,
                data_gaps_count=2,
            )
        )
        assert decision.is_promotable
        assert len(decision.reasons) == 4


class TestDeterminism:
    def test_same_input_same_output(self):
        facts = _facts(confidence="high", outcome="incorrect")
        d1 = classify_prediction_for_promotion(facts)
        d2 = classify_prediction_for_promotion(facts)
        assert d1 == d2

    def test_case_hash_deterministic(self):
        h1 = compute_case_hash("pred-1", ["reason_a", "reason_b"])
        h2 = compute_case_hash("pred-1", ["reason_b", "reason_a"])  # order-independent
        assert h1 == h2

    def test_case_hash_differs_by_prediction(self):
        h1 = compute_case_hash("pred-1", ["reason_a"])
        h2 = compute_case_hash("pred-2", ["reason_a"])
        assert h1 != h2

    def test_case_hash_differs_by_reasons(self):
        h1 = compute_case_hash("pred-1", ["reason_a"])
        h2 = compute_case_hash("pred-1", ["reason_b"])
        assert h1 != h2


class TestFactsFromRow:
    def test_builds_facts_from_dict_row(self):
        row = {
            "id": "abc-123",
            "ticker": "AAPL",
            "signal": "sell",
            "confidence": "high",
            "outcome": "incorrect",
            "realized_return": -0.02,
            "excess_return": -0.09,
            "citation_invalid_ratio": 0.5,
            "data_gaps_count": 1,
        }
        facts = facts_from_prediction_row(row)
        assert facts.prediction_id == "abc-123"
        assert facts.ticker == "AAPL"
        assert facts.outcome == "incorrect"

    def test_missing_outcome_defaults_to_neutral(self):
        row = {
            "id": "abc-123",
            "ticker": "AAPL",
            "signal": "hold",
            "confidence": "low",
            "outcome": None,
        }
        facts = facts_from_prediction_row(row)
        assert facts.outcome == "neutral"

    def test_missing_optional_fields_default_safely(self):
        row = {
            "id": "abc-123",
            "ticker": "AAPL",
            "signal": "hold",
            "confidence": "low",
            "outcome": "correct",
        }
        facts = facts_from_prediction_row(row)
        assert facts.realized_return is None
        assert facts.excess_return is None
        assert facts.citation_invalid_ratio is None
        assert facts.data_gaps_count == 0
