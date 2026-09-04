"""
Tests for the heuristic drift scorer (Tier 1 of the alert pipeline).
"""

from hypothesis import given, settings
from hypothesis import strategies as st
from src.alerts.drift_scorer import (
    DEFAULT_DRIFT_THRESHOLD,
    WEIGHTS,
    score_drift,
)


class TestWeights:
    def test_weights_sum_to_one(self):
        """A bad edit to WEIGHTS should fail CI loudly, not silently skew scoring."""
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


class TestScoreBounds:
    """Score must always be in [0.0, 1.0] regardless of input magnitude."""

    @given(
        previous_sentiment=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False),
        current_sentiment=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False),
        price_at_prediction=st.one_of(st.none(), st.floats(min_value=0.01, max_value=100000)),
        current_price=st.one_of(st.none(), st.floats(min_value=0.01, max_value=100000)),
        previous_risk_flag_count=st.integers(min_value=0, max_value=50),
        current_risk_flag_count=st.integers(min_value=0, max_value=50),
        new_sec_filing_detected=st.booleans(),
        previous_article_count=st.integers(min_value=0, max_value=1000),
        current_article_count=st.integers(min_value=0, max_value=1000),
        peer_signal_flipped=st.booleans(),
    )
    @settings(max_examples=200)
    def test_score_always_bounded(
        self,
        previous_sentiment,
        current_sentiment,
        price_at_prediction,
        current_price,
        previous_risk_flag_count,
        current_risk_flag_count,
        new_sec_filing_detected,
        previous_article_count,
        current_article_count,
        peer_signal_flipped,
    ):
        result = score_drift(
            previous_sentiment=previous_sentiment,
            current_sentiment=current_sentiment,
            price_at_prediction=price_at_prediction,
            current_price=current_price,
            previous_risk_flag_count=previous_risk_flag_count,
            current_risk_flag_count=current_risk_flag_count,
            new_sec_filing_detected=new_sec_filing_detected,
            previous_article_count=previous_article_count,
            current_article_count=current_article_count,
            peer_signal_flipped=peer_signal_flipped,
        )
        assert 0.0 <= result.score <= 1.0
        for value in (
            result.components.sentiment_delta,
            result.components.price_move_pct,
            result.components.risk_flag_count_delta,
            result.components.new_sec_filing,
            result.components.news_volume_spike,
            result.components.peer_signal_flip,
        ):
            assert 0.0 <= value <= 1.0

    @given(
        previous_sentiment=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False),
        current_sentiment=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False),
    )
    def test_determinism(self, previous_sentiment, current_sentiment):
        """Same inputs always produce the same score (no hidden randomness/state)."""
        r1 = score_drift(previous_sentiment=previous_sentiment, current_sentiment=current_sentiment)
        r2 = score_drift(previous_sentiment=previous_sentiment, current_sentiment=current_sentiment)
        assert r1.score == r2.score

    def test_no_change_scores_zero(self):
        result = score_drift(
            previous_sentiment=0.5,
            current_sentiment=0.5,
            price_at_prediction=100.0,
            current_price=100.0,
            previous_risk_flag_count=2,
            current_risk_flag_count=2,
            new_sec_filing_detected=False,
            previous_article_count=5,
            current_article_count=5,
            peer_signal_flipped=False,
        )
        assert result.score == 0.0
        assert result.likely_changed is False


class TestFixtureScenarios:
    """Realistic scenarios that should or shouldn't trigger escalation."""

    def test_clear_drift_scenario_exceeds_threshold(self):
        """Sentiment collapse + new risk flags + SEC filing = should escalate."""
        result = score_drift(
            previous_sentiment=0.8,
            current_sentiment=0.2,
            price_at_prediction=420.0,
            current_price=395.0,
            previous_risk_flag_count=1,
            current_risk_flag_count=4,
            new_sec_filing_detected=True,
            previous_article_count=3,
            current_article_count=15,
            peer_signal_flipped=False,
        )
        assert result.score > DEFAULT_DRIFT_THRESHOLD
        assert result.likely_changed is True

    def test_minor_noise_stays_below_threshold(self):
        """Small sentiment wobble and price noise shouldn't trigger the LLM judge."""
        result = score_drift(
            previous_sentiment=0.5,
            current_sentiment=0.52,
            price_at_prediction=100.0,
            current_price=101.0,
            previous_risk_flag_count=2,
            current_risk_flag_count=2,
            new_sec_filing_detected=False,
            previous_article_count=5,
            current_article_count=6,
            peer_signal_flipped=False,
        )
        assert result.score < DEFAULT_DRIFT_THRESHOLD
        assert result.likely_changed is False

    def test_new_sec_filing_alone_can_trigger(self):
        """A fresh 8-K alone (weight 0.15) shouldn't cross default 0.4 threshold,
        but combined with a modest price move it should."""
        result = score_drift(
            new_sec_filing_detected=True,
            price_at_prediction=50.0,
            current_price=54.0,  # 8% move
        )
        assert result.components.new_sec_filing == 1.0
        assert result.score < DEFAULT_DRIFT_THRESHOLD  # 0.15 + partial price component

    def test_peer_signal_flip_contributes(self):
        baseline = score_drift(peer_signal_flipped=False)
        flipped = score_drift(peer_signal_flipped=True)
        assert flipped.score > baseline.score
        assert flipped.components.peer_signal_flip == 1.0

    def test_price_move_saturates_at_ceiling(self):
        """Moves beyond the saturation point don't score above 1.0 for that component."""
        moderate = score_drift(price_at_prediction=100.0, current_price=110.0)  # 10% move
        extreme = score_drift(price_at_prediction=100.0, current_price=200.0)  # 100% move
        assert moderate.components.price_move_pct == 1.0
        assert extreme.components.price_move_pct == 1.0

    def test_missing_price_data_does_not_crash(self):
        result = score_drift(price_at_prediction=None, current_price=105.0)
        assert result.components.price_move_pct == 0.0
        result2 = score_drift(price_at_prediction=100.0, current_price=None)
        assert result2.components.price_move_pct == 0.0

    def test_zero_previous_articles_treated_as_moderate_spike(self):
        """Going from 0 prior coverage to some coverage shouldn't max out the
        component (avoids overweighting thinly-covered small caps)."""
        result = score_drift(previous_article_count=0, current_article_count=5)
        assert result.components.news_volume_spike == 0.5

    def test_custom_threshold_respected(self):
        result = score_drift(previous_sentiment=0.5, current_sentiment=0.65, threshold=0.05)
        assert result.threshold == 0.05
        assert result.likely_changed == (result.score >= 0.05)
