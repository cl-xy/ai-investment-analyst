"""
Heuristic drift scorer (Tier 1 of the alert evaluation pipeline).

Compares a previously-persisted ticker analysis against fresh, lightweight
probe data and produces a weighted drift score in [0.0, 1.0]. This is pure
Python with no I/O and no LLM calls — cheap enough to run on every monitored
ticker on every scheduled evaluation pass.

Only tickers whose score clears the configured threshold get escalated to
the (comparatively expensive) LLM drift judge in drift_judge.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.numeric import safe_float

# Default threshold above which a ticker is escalated to the LLM judge.
DEFAULT_DRIFT_THRESHOLD = 0.4

# Component weights. Must sum to 1.0 (enforced by a test, not at runtime,
# so a bad edit fails CI loudly rather than silently under/over-weighting).
WEIGHTS: dict[str, float] = {
    "sentiment_delta": 0.25,
    "price_move_pct": 0.20,
    "risk_flag_count_delta": 0.20,
    "new_sec_filing": 0.15,
    "news_volume_spike": 0.10,
    "peer_signal_flip": 0.10,
}

# Component-specific normalization constants.
_SENTIMENT_DELTA_SATURATION = 0.6  # |delta| >= this maps to component score 1.0
_PRICE_MOVE_SATURATION_PCT = 10.0  # |% move| >= this maps to component score 1.0
_RISK_FLAG_DELTA_SATURATION = 3  # |count delta| >= this maps to component score 1.0
_NEWS_VOLUME_SATURATION = 3.0  # articles_now / articles_before >= this maps to 1.0


@dataclass(frozen=True, slots=True)
class DriftComponents:
    """Per-component sub-scores in [0.0, 1.0], before weighting."""

    sentiment_delta: float = 0.0
    price_move_pct: float = 0.0
    risk_flag_count_delta: float = 0.0
    new_sec_filing: float = 0.0
    news_volume_spike: float = 0.0
    peer_signal_flip: float = 0.0


@dataclass(frozen=True, slots=True)
class DriftResult:
    """Final scoring result: weighted total plus the raw component breakdown."""

    score: float
    components: DriftComponents
    likely_changed: bool
    threshold: float
    details: dict = field(default_factory=dict)


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _score_sentiment_delta(previous_sentiment: float, current_sentiment: float) -> float:
    """Linear ramp from 0 at delta=0 to 1.0 at |delta| >= saturation."""
    delta = abs(safe_float(current_sentiment) - safe_float(previous_sentiment))
    if _SENTIMENT_DELTA_SATURATION <= 0:
        return 0.0
    return _clamp01(delta / _SENTIMENT_DELTA_SATURATION)


def _score_price_move(price_at_prediction: float | None, current_price: float | None) -> float:
    """Linear ramp on absolute percentage move since the analysis was made."""
    if not price_at_prediction or not current_price:
        return 0.0
    if price_at_prediction <= 0:
        return 0.0
    pct_move = abs((current_price - price_at_prediction) / price_at_prediction) * 100.0
    return _clamp01(pct_move / _PRICE_MOVE_SATURATION_PCT)


def _score_risk_flag_delta(previous_count: int, current_count: int) -> float:
    """Linear ramp on absolute change in the number of risk flags."""
    delta = abs(current_count - previous_count)
    if _RISK_FLAG_DELTA_SATURATION <= 0:
        return 0.0
    return _clamp01(delta / _RISK_FLAG_DELTA_SATURATION)


def _score_new_sec_filing(new_filing_detected: bool) -> float:
    """Binary signal: any new filing since the last analysis maxes this component."""
    return 1.0 if new_filing_detected else 0.0


def _score_news_volume_spike(previous_article_count: int, current_article_count: int) -> float:
    """Ratio-based ramp: current volume relative to the prior baseline.

    Guards against div-by-zero when there was no prior news (treats any new
    coverage appearing from a zero baseline as a moderate, not maximal,
    spike to avoid overweighting thinly-covered small caps).
    """
    if previous_article_count <= 0:
        return 0.5 if current_article_count > 0 else 0.0
    ratio = current_article_count / previous_article_count
    if ratio <= 1.0:
        return 0.0
    return _clamp01((ratio - 1.0) / (_NEWS_VOLUME_SATURATION - 1.0))


def _score_peer_signal_flip(peer_flipped: bool) -> float:
    """Binary signal: a sector peer's signal flipped since our last analysis."""
    return 1.0 if peer_flipped else 0.0


def score_drift(
    *,
    previous_sentiment: float = 0.0,
    current_sentiment: float = 0.0,
    price_at_prediction: float | None = None,
    current_price: float | None = None,
    previous_risk_flag_count: int = 0,
    current_risk_flag_count: int = 0,
    new_sec_filing_detected: bool = False,
    previous_article_count: int = 0,
    current_article_count: int = 0,
    peer_signal_flipped: bool = False,
    threshold: float = DEFAULT_DRIFT_THRESHOLD,
) -> DriftResult:
    """Compute the weighted drift score from raw, already-fetched inputs.

    Pure function: no I/O. Callers (the pipeline / data_probe) are
    responsible for gathering the raw values first.
    """
    components = DriftComponents(
        sentiment_delta=_score_sentiment_delta(previous_sentiment, current_sentiment),
        price_move_pct=_score_price_move(price_at_prediction, current_price),
        risk_flag_count_delta=_score_risk_flag_delta(
            previous_risk_flag_count, current_risk_flag_count
        ),
        new_sec_filing=_score_new_sec_filing(new_sec_filing_detected),
        news_volume_spike=_score_news_volume_spike(
            previous_article_count, current_article_count
        ),
        peer_signal_flip=_score_peer_signal_flip(peer_signal_flipped),
    )

    total = (
        components.sentiment_delta * WEIGHTS["sentiment_delta"]
        + components.price_move_pct * WEIGHTS["price_move_pct"]
        + components.risk_flag_count_delta * WEIGHTS["risk_flag_count_delta"]
        + components.new_sec_filing * WEIGHTS["new_sec_filing"]
        + components.news_volume_spike * WEIGHTS["news_volume_spike"]
        + components.peer_signal_flip * WEIGHTS["peer_signal_flip"]
    )
    total = _clamp01(total)

    return DriftResult(
        score=total,
        components=components,
        likely_changed=total >= threshold,
        threshold=threshold,
        details={
            "sentiment_delta_raw": abs(
                safe_float(current_sentiment) - safe_float(previous_sentiment)
            ),
            "price_move_pct_raw": (
                abs((current_price - price_at_prediction) / price_at_prediction) * 100.0
                if price_at_prediction and current_price and price_at_prediction > 0
                else None
            ),
            "risk_flag_count_delta_raw": current_risk_flag_count - previous_risk_flag_count,
            "new_sec_filing_detected": new_sec_filing_detected,
            "article_count_previous": previous_article_count,
            "article_count_current": current_article_count,
            "peer_signal_flipped": peer_signal_flipped,
        },
    )
