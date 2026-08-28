"""
Shared helper: fetch the most recent persisted analysis for a ticker.

Used by multiple triggers (and the pipeline) as the "previous state"
baseline to diff fresh probe data against. Centralized here so every
trigger agrees on what "the last known analysis" means.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from src.db import fetchrow


@dataclass(frozen=True, slots=True)
class LastAnalysisSnapshot:
    """Minimal projection of the most recent ticker_analyses row needed by
    the alert pipeline. Not the full TickerAnalysis shape — just what
    triggers/scorer need."""

    ticker: str
    signal: str
    confidence: str
    sentiment_score: float
    risk_flags: list[str]
    price_data: dict
    fundamentals: dict
    analysis_id: str
    created_at: datetime


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


async def get_last_analysis(ticker: str) -> LastAnalysisSnapshot | None:
    """Return the most recent non-insufficient_data analysis for `ticker`,
    or None if the ticker has never been successfully analyzed."""
    row = await fetchrow(
        """
        SELECT ta.ticker, ta.signal, ta.confidence, ta.sentiment_score,
               ta.risk_flags, ta.price_data, ta.fundamentals, ta.analysis_id, a.created_at
        FROM ticker_analyses ta
        JOIN analyses a ON ta.analysis_id = a.id
        WHERE ta.ticker = $1 AND ta.signal != 'insufficient_data'
        ORDER BY a.created_at DESC
        LIMIT 1
        """,
        ticker,
    )
    if row is None:
        return None

    return LastAnalysisSnapshot(
        ticker=row["ticker"],
        signal=row["signal"],
        confidence=row["confidence"],
        sentiment_score=row["sentiment_score"] or 0.0,
        risk_flags=_as_list(row["risk_flags"]),
        price_data=_as_dict(row["price_data"]),
        fundamentals=_as_dict(row["fundamentals"]),
        analysis_id=str(row["analysis_id"]),
        created_at=row["created_at"],
    )


async def get_latest_signals_for_tickers(tickers: list[str]) -> dict[str, str]:
    """Batch lookup: return {ticker: signal} for the most recent analysis of
    each ticker in `tickers`. Used by peer_trigger to check sector peers
    without N sequential round-trips."""
    if not tickers:
        return {}
    result: dict[str, str] = {}
    for ticker in tickers:
        snapshot = await get_last_analysis(ticker)
        if snapshot is not None:
            result[ticker] = snapshot.signal
    return result


async def get_signal_as_of(ticker: str, as_of: datetime) -> str | None:
    """Return the signal for `ticker` from the most recent analysis that was
    created at or before `as_of`. Used to establish "what was this peer's
    signal around the time of our own last analysis" as a flip baseline."""
    row = await fetchrow(
        """
        SELECT ta.signal
        FROM ticker_analyses ta
        JOIN analyses a ON ta.analysis_id = a.id
        WHERE ta.ticker = $1 AND ta.signal != 'insufficient_data' AND a.created_at <= $2
        ORDER BY a.created_at DESC
        LIMIT 1
        """,
        ticker,
        as_of,
    )
    return row["signal"] if row else None
