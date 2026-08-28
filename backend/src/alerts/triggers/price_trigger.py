"""
Price trigger: detects a large move since the price recorded at the time
of the ticker's last analysis (not a live intraday feed — this piggybacks
on the same price_data snapshot the debate used, via extract_current_price).
"""

from __future__ import annotations

from src.alerts.data_probe import ProbeResult
from src.alerts.last_analysis import LastAnalysisSnapshot
from src.alerts.triggers.events import TriggerEvent
from src.api.persistence import extract_current_price

_PRICE_MOVE_THRESHOLD_PCT = 5.0


def check_price_trigger(
    snapshot: LastAnalysisSnapshot | None, probe: ProbeResult
) -> TriggerEvent | None:
    if snapshot is None or probe.current_price is None:
        return None

    price_at_analysis = extract_current_price(snapshot.price_data)
    if not price_at_analysis or price_at_analysis <= 0:
        return None

    pct_move = (probe.current_price - price_at_analysis) / price_at_analysis * 100.0
    if abs(pct_move) < _PRICE_MOVE_THRESHOLD_PCT:
        return None

    direction = "up" if pct_move > 0 else "down"
    return TriggerEvent(
        ticker=probe.ticker,
        trigger_type="price",
        summary=f"Price moved {direction} {abs(pct_move):.1f}% since last analysis",
        metadata={
            "price_at_analysis": price_at_analysis,
            "current_price": probe.current_price,
            "pct_move": pct_move,
        },
    )
