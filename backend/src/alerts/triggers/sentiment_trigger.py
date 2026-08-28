"""
Sentiment trigger: detects a large swing in retail sentiment (StockTwits)
since the ticker's last analysis.
"""

from __future__ import annotations

from src.alerts.data_probe import ProbeResult
from src.alerts.last_analysis import LastAnalysisSnapshot
from src.alerts.triggers.events import TriggerEvent

# Matches drift_scorer's saturation point loosely, but this is a coarser
# binary gate — the actual weighting happens in the scorer. This just
# decides whether the shift is even worth surfacing as a named "event."
_SENTIMENT_SPIKE_THRESHOLD = 0.3


def check_sentiment_trigger(
    snapshot: LastAnalysisSnapshot | None, probe: ProbeResult
) -> TriggerEvent | None:
    if snapshot is None or probe.sentiment_score is None:
        return None

    delta = probe.sentiment_score - snapshot.sentiment_score
    if abs(delta) < _SENTIMENT_SPIKE_THRESHOLD:
        return None

    direction = "improved" if delta > 0 else "deteriorated"
    return TriggerEvent(
        ticker=probe.ticker,
        trigger_type="sentiment",
        summary=(
            f"Retail sentiment {direction}: {snapshot.sentiment_score:.2f} -> "
            f"{probe.sentiment_score:.2f}"
        ),
        metadata={
            "previous_sentiment": snapshot.sentiment_score,
            "current_sentiment": probe.sentiment_score,
            "delta": delta,
        },
    )
