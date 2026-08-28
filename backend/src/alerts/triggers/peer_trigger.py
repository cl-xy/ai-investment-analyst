"""
Peer signal trigger: detects sector-peer contamination — e.g. AMD's signal
flipping from buy to sell might be relevant context for NVDA even if NVDA's
own numbers haven't moved yet. Reuses the static SECTOR_PEERS map (no extra
network calls) and the existing ticker_analyses history for peers' signals.
"""

from __future__ import annotations

from src.agent.peer_map import get_sector_peers
from src.alerts.last_analysis import (
    LastAnalysisSnapshot,
    get_last_analysis,
    get_signal_as_of,
)
from src.alerts.triggers.events import TriggerEvent

_MAX_PEERS_CHECKED = 3


async def check_peer_signal_trigger(
    snapshot: LastAnalysisSnapshot | None, ticker: str
) -> TriggerEvent | None:
    """Fire if any sector peer's current signal differs from what that
    peer's signal was around the time of our own last analysis.

    Without a prior analysis for `ticker` there's no sector context and no
    "as of" timestamp to baseline against, so this is skipped.
    """
    if snapshot is None:
        return None

    sector = snapshot.fundamentals.get("sector") if isinstance(snapshot.fundamentals, dict) else None
    peers = get_sector_peers(sector, exclude={ticker}, limit=_MAX_PEERS_CHECKED)
    if not peers:
        return None

    for peer in peers:
        peer_snapshot = await get_last_analysis(peer)
        if peer_snapshot is None:
            continue
        baseline_signal = await get_signal_as_of(peer, snapshot.created_at)
        if baseline_signal is None or baseline_signal == peer_snapshot.signal:
            continue

        return TriggerEvent(
            ticker=ticker,
            trigger_type="peer_signal",
            summary=(
                f"Sector peer {peer} flipped {baseline_signal} -> {peer_snapshot.signal}"
            ),
            metadata={
                "peer": peer,
                "peer_previous_signal": baseline_signal,
                "peer_current_signal": peer_snapshot.signal,
                "sector": sector,
            },
        )

    return None
