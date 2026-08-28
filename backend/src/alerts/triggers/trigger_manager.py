"""
Trigger manager: runs all event trigger monitors for a set of tickers and
aggregates the fired events. This is the "Event Bus" layer in the alert
pipeline architecture — it doesn't score or judge anything, it just answers
"what changed" per ticker.
"""

from __future__ import annotations

import asyncio

from src.alerts.data_probe import ProbeResult, probe_tickers
from src.alerts.last_analysis import LastAnalysisSnapshot, get_last_analysis
from src.alerts.triggers.events import TriggerEvent
from src.alerts.triggers.peer_trigger import check_peer_signal_trigger
from src.alerts.triggers.price_trigger import check_price_trigger
from src.alerts.triggers.sec_trigger import check_sec_filing_trigger
from src.alerts.triggers.sentiment_trigger import check_sentiment_trigger
from src.logging_config import get_logger

log = get_logger(__name__)


async def check_all_triggers_for_ticker(
    ticker: str, snapshot: LastAnalysisSnapshot | None, probe: ProbeResult
) -> list[TriggerEvent]:
    """Run all trigger checks for a single ticker (given a pre-fetched
    snapshot and probe) and return every event that fired."""
    events: list[TriggerEvent] = []

    sec_event = check_sec_filing_trigger(snapshot, probe)
    if sec_event:
        events.append(sec_event)

    sentiment_event = check_sentiment_trigger(snapshot, probe)
    if sentiment_event:
        events.append(sentiment_event)

    price_event = check_price_trigger(snapshot, probe)
    if price_event:
        events.append(price_event)

    try:
        peer_event = await check_peer_signal_trigger(snapshot, ticker)
        if peer_event:
            events.append(peer_event)
    except Exception:
        log.warning("peer_trigger_failed ticker=%s", ticker, exc_info=True)

    return events


async def check_all_triggers(tickers: list[str]) -> dict[str, list[TriggerEvent]]:
    """Run all trigger checks across `tickers` with bounded concurrency for
    the probe fetch (peer/sec/sentiment lookups run per-ticker inline)."""
    if not tickers:
        return {}

    probes = await probe_tickers(tickers)

    snapshots: dict[str, LastAnalysisSnapshot | None] = {}
    for ticker in tickers:
        try:
            snapshots[ticker] = await get_last_analysis(ticker)
        except Exception:
            log.warning("last_analysis_lookup_failed ticker=%s", ticker, exc_info=True)
            snapshots[ticker] = None

    semaphore = asyncio.Semaphore(3)

    async def _bounded(ticker: str) -> tuple[str, list[TriggerEvent]]:
        async with semaphore:
            probe = probes.get(ticker)
            if probe is None:
                return ticker, []
            events = await check_all_triggers_for_ticker(ticker, snapshots.get(ticker), probe)
            return ticker, events

    results = await asyncio.gather(*[_bounded(t) for t in tickers], return_exceptions=True)

    out: dict[str, list[TriggerEvent]] = {}
    for item in results:
        if isinstance(item, BaseException):
            log.warning("trigger_check_task_failed error=%s", item)
            continue
        ticker, events = item
        out[ticker] = events
    return out
