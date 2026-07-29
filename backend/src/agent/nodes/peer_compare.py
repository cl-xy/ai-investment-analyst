"""
Auto sector-peer comparison node.

Runs only when exactly one ticker was requested (single-ticker analysis),
after `debate` and before `generate_report`. Surfaces 1-2 sector peers for
context WITHOUT running a full bull/bear/moderator debate for them:

  1. Reuse a recent (<3 day old) cached ticker_analyses row if one exists —
     zero extra cost.
  2. Otherwise fetch fundamentals-only (price, P/E, growth, margin) directly
     via the yfinance client — no debate, no LLM call, and deliberately NOT
     routed through market_server's Alpha Vantage fallback so a yfinance
     hiccup on peer data can't eat into the primary ticker's AV budget.

Peer snapshots are never persisted to ticker_analyses — that table implies a
real debate happened, and the calibration/track-record system assumes every
row produced a signal.
"""

import asyncio
import json

from src.db import fetchrow
from src.logging_config import get_logger
from src.mcp_servers.market_server.sources import yfinance_client as yf_client

from ..peer_map import get_sector_peers
from ..peer_schemas import PeerComparisonResult, PeerSnapshot
from ..state import InvestmentAnalystState

log = get_logger(__name__)

_RECENT_ANALYSIS_DAYS = 3
_MAX_PEERS = 2


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


async def _recent_cached_peer(ticker: str) -> PeerSnapshot | None:
    """Reuse a recent real analysis of this peer if one exists."""
    row = await fetchrow(
        """
        SELECT ta.ticker, ta.signal, ta.confidence, ta.price_data, ta.fundamentals
        FROM ticker_analyses ta
        JOIN analyses a ON ta.analysis_id = a.id
        WHERE ta.ticker = $1 AND ta.signal != 'insufficient_data'
          AND a.created_at > now() - make_interval(days => $2::int)
        ORDER BY a.created_at DESC
        LIMIT 1
        """,
        ticker,
        _RECENT_ANALYSIS_DAYS,
    )
    if not row:
        return None
    price_data = _as_dict(row["price_data"])
    fundamentals = _as_dict(row["fundamentals"])
    return PeerSnapshot(
        ticker=row["ticker"],
        source="cached_analysis",
        signal=row["signal"],
        confidence=row["confidence"],
        current_price=price_data.get("current_price"),
        pe_ratio=price_data.get("pe_ratio"),
        revenue_growth_yoy=fundamentals.get("revenue_growth_yoy"),
        profit_margin=fundamentals.get("profit_margin"),
    )


async def _fundamentals_only_peer(ticker: str) -> PeerSnapshot | None:
    """Cheap, debate-free peer context: yfinance only, no Alpha Vantage fallback."""
    try:
        quote, fundamentals = await asyncio.gather(
            asyncio.to_thread(yf_client.get_quote, ticker),
            asyncio.to_thread(yf_client.get_fundamentals, ticker),
        )
    except Exception as e:
        log.warning("peer_fundamentals_fetch_failed ticker=%s error=%s", ticker, e)
        return None

    if not quote and not fundamentals:
        return None

    return PeerSnapshot(
        ticker=ticker,
        source="fundamentals_only",
        current_price=quote.get("current_price"),
        pe_ratio=quote.get("pe_ratio"),
        revenue_growth_yoy=fundamentals.get("revenue_growth_yoy"),
        profit_margin=fundamentals.get("profit_margin"),
    )


async def _get_peer_snapshot(ticker: str) -> PeerSnapshot | None:
    snapshot = await _recent_cached_peer(ticker)
    if snapshot is not None:
        return snapshot
    return await _fundamentals_only_peer(ticker)


async def peer_compare_node(state: InvestmentAnalystState) -> dict:
    tickers = state.get("tickers_to_analyze", [])
    if len(tickers) != 1:
        return {}

    primary = tickers[0]
    primary_analysis = state.get("ticker_analyses", {}).get(primary)
    if not primary_analysis:
        return {}

    correlation_id = state.get("correlation_id")
    _log = (
        log.bind(correlation_id=correlation_id, node="peer_compare", ticker=primary)
        if correlation_id
        else log
    )

    sector = (primary_analysis.get("fundamentals") or {}).get("sector")
    if not sector:
        return {}

    peer_tickers = get_sector_peers(sector, exclude={primary}, limit=_MAX_PEERS)
    if not peer_tickers:
        return {}

    try:
        results = await asyncio.gather(*[_get_peer_snapshot(t) for t in peer_tickers])
    except Exception as e:
        # Supplementary only — never block the analysis on peer enrichment.
        _log.warning("peer_compare_failed", error=str(e))
        return {}

    peers = [p for p in results if p is not None]
    if not peers:
        return {}

    result = PeerComparisonResult(primary=primary, sector=sector, peers=peers)
    return {"peer_comparison": result.model_dump()}
