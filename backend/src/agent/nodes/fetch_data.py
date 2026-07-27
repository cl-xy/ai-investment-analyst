"""
Fetch data node. Calls 5 MCP tool servers in parallel with graceful degradation.

Each tool call is independently wrapped with timeout handling.
Integrates with the PostgreSQL cache layer (stale-while-revalidate).
Partial failures produce data_gaps rather than crashing the analysis.
"""

import asyncio
import json
import logging
import time

from src.cache.manager import cache_manager

from ..state import InvestmentAnalystState

log = logging.getLogger(__name__)

TOOL_TIMEOUT = 30  # seconds per tool call


def _unwrap(result) -> dict | list:
    """Unwrap LangChain MCP content-block format: [{'type':'text','text':'<json>'}]."""
    if isinstance(result, list) and result and isinstance(result[0], dict) and "type" in result[0]:
        for block in result:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, ValueError):
                    return block["text"]
        return {}
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (json.JSONDecodeError, ValueError):
            return result
    return result


async def _call_tool_raw(tools: dict, name: str, **kwargs) -> tuple[dict | list, bool, int]:
    """
    Call a single MCP tool directly (no cache) with timeout.
    Returns (result, success, duration_ms).
    """
    tool = tools.get(name)
    if tool is None:
        return {}, False, 0

    start = time.monotonic()
    try:
        raw = await asyncio.wait_for(tool.ainvoke(kwargs), timeout=TOOL_TIMEOUT)
        duration_ms = int((time.monotonic() - start) * 1000)
        return _unwrap(raw), True, duration_ms
    except asyncio.TimeoutError:
        duration_ms = int((time.monotonic() - start) * 1000)
        return {"error": f"Timeout after {TOOL_TIMEOUT}s"}, False, duration_ms
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        return {"error": str(e)}, False, duration_ms


async def _call_tool_cached(
    tools: dict, provider: str, tool_name: str, ticker: str, tool_kwargs: dict
) -> tuple[dict | list, bool, int, bool]:
    """
    Call a tool through the cache layer.
    Returns (result, success, duration_ms, was_cached).
    """
    start = time.monotonic()

    async def _fetch():
        data, success, _ = await _call_tool_raw(tools, tool_name, **tool_kwargs)
        if not success:
            raise RuntimeError(f"Tool {tool_name} failed")
        return data

    try:
        data, source_id, was_cached = await cache_manager.get_or_fetch(
            provider=provider,
            tool=tool_name,
            ticker=ticker,
            fetch_fn=_fetch,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return data, True, duration_ms, was_cached
    except Exception:
        # Cache miss + fetch failure: fall back to direct call
        data, success, duration_ms = await _call_tool_raw(tools, tool_name, **tool_kwargs)
        return data, success, duration_ms, False


async def fetch_data_node(state: InvestmentAnalystState, *, mcp_tools: dict) -> dict:
    tickers = state.get("tickers_to_analyze", [])
    if not tickers:
        return {}

    # Budget-exhaustion fallback: if providers are nearly depleted, serve cache-only
    cache_only = False
    try:
        from src.cache.budget import check_budget

        budgets_ok = await asyncio.gather(
            check_budget("newsapi"),
            check_budget("groq"),
        )
        cache_only = not all(budgets_ok)
    except Exception as e:
        log.warning("budget_check_failed: %s", e)

    async def fetch_one(ticker: str) -> tuple[str, list, dict, str, list[str]]:
        """Fetch all data for one ticker with caching. Returns per-ticker results + gaps."""
        gaps: list[str] = []

        if cache_only:
            # Budget exhausted: serve only from cache, no live API calls
            from src.cache.manager import cache_manager as cm

            news_data, _, news_hit = await cm.get_cached_only("newsapi", "get_ticker_news", ticker)
            quote_data, _, quote_hit = await cm.get_cached_only("yfinance", "get_quote", ticker)
            fundamentals_data, _, fund_hit = await cm.get_cached_only(
                "yfinance", "get_fundamentals", ticker
            )
            filing_data, _, filing_hit = await cm.get_cached_only(
                "sec_edgar", "get_latest_filing_summary", ticker
            )
            indicators_data, _, ind_hit = await cm.get_cached_only(
                "yfinance", "get_technical_indicators", ticker
            )

            if not news_hit:
                gaps.append(f"News data unavailable for {ticker} (budget exhausted)")
                news_data = []
            if not quote_hit:
                gaps.append(f"Price quote unavailable for {ticker} (budget exhausted)")
                quote_data = {}
            if not fund_hit:
                gaps.append(f"Fundamentals unavailable for {ticker} (budget exhausted)")
                fundamentals_data = {}
            if not filing_hit:
                gaps.append(f"SEC filing unavailable for {ticker} (budget exhausted)")
                filing_data = {}
            if not ind_hit:
                gaps.append(f"Technical indicators unavailable for {ticker} (budget exhausted)")
                indicators_data = {}

            news = news_data if isinstance(news_data, list) else []
            prices = {
                "quote": quote_data if isinstance(quote_data, dict) else {},
                "fundamentals": fundamentals_data if isinstance(fundamentals_data, dict) else {},
                "indicators": indicators_data if isinstance(indicators_data, dict) else {},
            }
            filing_text = (
                filing_data.get("text_excerpt", "") if isinstance(filing_data, dict) else ""
            )
            return ticker, news, prices, filing_text, gaps

        # Normal path: fetch through cache layer
        results = await asyncio.gather(
            _call_tool_cached(
                mcp_tools,
                "newsapi",
                "get_ticker_news",
                ticker,
                {"ticker": ticker, "days_back": 7, "max_articles": 10},
            ),
            _call_tool_cached(mcp_tools, "yfinance", "get_quote", ticker, {"ticker": ticker}),
            _call_tool_cached(
                mcp_tools, "yfinance", "get_fundamentals", ticker, {"ticker": ticker}
            ),
            _call_tool_cached(
                mcp_tools,
                "sec_edgar",
                "get_latest_filing_summary",
                ticker,
                {"ticker": ticker, "form_type": "10-K"},
            ),
            _call_tool_cached(
                mcp_tools, "yfinance", "get_technical_indicators", ticker, {"ticker": ticker}
            ),
        )

        news_data, news_ok, _, _ = results[0]
        quote_data, quote_ok, _, _ = results[1]
        fundamentals_data, fundamentals_ok, _, _ = results[2]
        filing_data, filing_ok, _, _ = results[3]
        indicators_data, indicators_ok, _, _ = results[4]

        # Track gaps for failed sources
        if not news_ok:
            gaps.append(f"News data unavailable for {ticker}")
            news_data = []
        if not quote_ok:
            gaps.append(f"Price quote unavailable for {ticker}")
            quote_data = {}
        if not fundamentals_ok:
            gaps.append(f"Fundamentals unavailable for {ticker}")
            fundamentals_data = {}
        if not filing_ok:
            gaps.append(f"SEC filing unavailable for {ticker}")
            filing_data = {}
        if not indicators_ok:
            gaps.append(f"Technical indicators unavailable for {ticker}")
            indicators_data = {}

        news = news_data if isinstance(news_data, list) else []
        prices = {
            "quote": quote_data if isinstance(quote_data, dict) else {},
            "fundamentals": fundamentals_data if isinstance(fundamentals_data, dict) else {},
            "indicators": indicators_data if isinstance(indicators_data, dict) else {},
        }
        filing_text = filing_data.get("text_excerpt", "") if isinstance(filing_data, dict) else ""

        return ticker, news, prices, filing_text, gaps

    all_results = await asyncio.gather(*[fetch_one(t) for t in tickers])

    raw_news = {}
    raw_prices = {}
    raw_filings = {}
    all_gaps: list[str] = []

    for ticker, news, prices, filing_text, gaps in all_results:
        raw_news[ticker] = news
        raw_prices[ticker] = prices
        raw_filings[ticker] = filing_text
        all_gaps.extend(gaps)

    return {
        "raw_news": raw_news,
        "raw_prices": raw_prices,
        "raw_filings": raw_filings,
        "data_gaps": all_gaps,
    }
