"""
Lightweight data probe for alert evaluation.

Fetches the *minimum* fresh data needed by the heuristic drift scorer
(drift_scorer.py) without running the full LangGraph analysis pipeline and
without any LLM calls. Designed to complete in well under 5 seconds per
ticker so it's cheap enough to run against an entire watchlist/portfolio on
every scheduled evaluation pass.

Sources reused directly from the existing MCP tool server internals (not
through the MCP protocol layer, since this is an internal caller, not an
agent tool call):
  - yfinance_client.get_quote           -> current price
  - stocktwits.get_ticker_sentiment     -> retail sentiment snapshot
  - edgar_client.search_filings         -> latest filing date (SEC drop detection)
  - news RSS/NewsAPI fallback chain     -> recent article count

Each sub-fetch is independently exception-isolated: a failure in one source
degrades that field to None/0 rather than failing the whole probe, mirroring
the graceful-degradation pattern used in fetch_data.py.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from cachetools import TTLCache

from src.logging_config import get_logger
from src.mcp_servers.market_server.sources import yfinance_client as yf_client
from src.mcp_servers.news_server.server import _fetch_ticker_news
from src.mcp_servers.sec_server.edgar_client import search_filings
from src.mcp_servers.sentiment_server.sources import stocktwits

log = get_logger(__name__)

_PROBE_TIMEOUT = 5.0  # seconds per sub-fetch
_CACHE_TTL_SECONDS = 900  # 15 minutes

# Own cache, separate from the analysis pipeline's Postgres SWR cache. This
# is intentionally simple/in-process: alert evaluation is best-effort and
# tolerates a cold cache after a process restart.
_probe_cache: TTLCache = TTLCache(maxsize=256, ttl=_CACHE_TTL_SECONDS)


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Fresh, lightweight snapshot used as scorer input. Any field may be
    None/0/empty if that source was unavailable — callers must tolerate
    partial data rather than treating it as a hard failure."""

    ticker: str
    current_price: float | None
    sentiment_score: float | None  # normalized to [-1, 1] via bullish_ratio, or None
    latest_filing_date: str | None  # ISO date string, or None if lookup failed
    latest_filing_form_type: str | None
    article_count: int
    fetched_at: float  # time.monotonic() timestamp
    data_gaps: list[str]


def _bullish_ratio_to_sentiment(bullish_ratio: float | None) -> float | None:
    """Map StockTwits bullish_ratio [0,1] to a [-1,1] sentiment scale so it's
    comparable with the debate's sentiment_score field."""
    if bullish_ratio is None:
        return None
    return round((bullish_ratio * 2.0) - 1.0, 4)


async def _fetch_price(ticker: str) -> tuple[float | None, list[str]]:
    gaps: list[str] = []
    try:
        quote = await asyncio.wait_for(
            asyncio.to_thread(yf_client.get_quote, ticker), timeout=_PROBE_TIMEOUT
        )
        price = quote.get("price") if isinstance(quote, dict) else None
        if price is None:
            gaps.append("probe_price_unavailable")
        return price, gaps
    except Exception as exc:
        log.warning("probe_price_failed ticker=%s error=%s", ticker, exc)
        return None, ["probe_price_fetch_failed"]


async def _fetch_sentiment(ticker: str) -> tuple[float | None, list[str]]:
    gaps: list[str] = []
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(stocktwits.get_ticker_sentiment, ticker), timeout=_PROBE_TIMEOUT
        )
        bullish_ratio = result.get("bullish_ratio") if isinstance(result, dict) else None
        sentiment = _bullish_ratio_to_sentiment(bullish_ratio)
        if sentiment is None:
            gaps.append("probe_sentiment_unavailable")
        return sentiment, gaps
    except Exception as exc:
        log.warning("probe_sentiment_failed ticker=%s error=%s", ticker, exc)
        return None, ["probe_sentiment_fetch_failed"]


async def _fetch_latest_filing(ticker: str) -> tuple[str | None, str | None, list[str]]:
    gaps: list[str] = []
    try:
        # 8-K covers material events; 10-Q covers quarterly financials. Check
        # both and report whichever is more recent, since either can move a thesis.
        results: list[dict] = []
        for form_type in ("8-K", "10-Q"):
            filings = await asyncio.wait_for(
                asyncio.to_thread(search_filings, ticker, form_type, 1), timeout=_PROBE_TIMEOUT
            )
            if isinstance(filings, list) and filings:
                first = filings[0]
                if isinstance(first, dict) and first.get("filed_date"):
                    results.append(first)

        if not results:
            gaps.append("probe_no_recent_filings")
            return None, None, gaps

        latest = max(results, key=lambda f: f.get("filed_date", ""))
        return latest.get("filed_date"), latest.get("form_type"), gaps
    except Exception as exc:
        log.warning("probe_filing_failed ticker=%s error=%s", ticker, exc)
        return None, None, ["probe_filing_fetch_failed"]


async def _fetch_article_count(ticker: str) -> tuple[int, list[str]]:
    gaps: list[str] = []
    try:
        articles = await asyncio.wait_for(
            asyncio.to_thread(_fetch_ticker_news, ticker, 3, 20), timeout=_PROBE_TIMEOUT
        )
        count = len(articles) if isinstance(articles, list) else 0
        return count, gaps
    except Exception as exc:
        log.warning("probe_news_failed ticker=%s error=%s", ticker, exc)
        return 0, ["probe_news_fetch_failed"]


async def probe_ticker(ticker: str, *, force_refresh: bool = False) -> ProbeResult:
    """Fetch a fresh lightweight snapshot for `ticker`, using a 15-minute
    in-process cache unless force_refresh is set."""
    ticker = ticker.strip().upper()
    cache_key = ticker

    if not force_refresh:
        cached = _probe_cache.get(cache_key)
        if cached is not None:
            return cached

    price, price_gaps = await _fetch_price(ticker)
    sentiment, sentiment_gaps = await _fetch_sentiment(ticker)
    filing_date, filing_form, filing_gaps = await _fetch_latest_filing(ticker)
    article_count, news_gaps = await _fetch_article_count(ticker)

    result = ProbeResult(
        ticker=ticker,
        current_price=price,
        sentiment_score=sentiment,
        latest_filing_date=filing_date,
        latest_filing_form_type=filing_form,
        article_count=article_count,
        fetched_at=time.monotonic(),
        data_gaps=[*price_gaps, *sentiment_gaps, *filing_gaps, *news_gaps],
    )
    _probe_cache[cache_key] = result
    return result


async def probe_tickers(tickers: list[str], *, concurrency: int = 3) -> dict[str, ProbeResult]:
    """Probe multiple tickers with bounded concurrency to avoid hammering
    external APIs (mirrors the semaphore pattern in fetch_data.py)."""
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(ticker: str) -> tuple[str, ProbeResult]:
        async with semaphore:
            return ticker, await probe_ticker(ticker)

    results = await asyncio.gather(*[_bounded(t) for t in tickers], return_exceptions=True)
    out: dict[str, ProbeResult] = {}
    for item in results:
        if isinstance(item, BaseException):
            log.warning("probe_tickers_task_failed error=%s", item)
            continue
        ticker, result = item
        out[ticker] = result
    return out
