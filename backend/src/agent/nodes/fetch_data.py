"""
Fetch data node — calls 5 MCP tool servers in parallel with graceful degradation.

Each tool call is independently wrapped. Partial failures produce data_gaps
rather than crashing the entire analysis.
"""

import asyncio
import json
import time

from ..state import InvestmentAnalystState

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


async def _call_tool(tools: dict, name: str, **kwargs) -> tuple[dict | list, bool, int]:
    """
    Call a single MCP tool with timeout.
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


async def fetch_data_node(state: InvestmentAnalystState, *, mcp_tools: dict) -> dict:
    tickers = state.get("tickers_to_analyze", [])
    if not tickers:
        return {}

    async def fetch_one(ticker: str) -> tuple[str, dict, dict, dict, str, dict, list[str]]:
        """Fetch all data for one ticker. Returns per-ticker results + gaps."""
        gaps: list[str] = []

        # Run all tool calls in parallel
        results = await asyncio.gather(
            _call_tool(mcp_tools, "get_ticker_news", ticker=ticker, days_back=7, max_articles=10),
            _call_tool(mcp_tools, "get_quote", ticker=ticker),
            _call_tool(mcp_tools, "get_fundamentals", ticker=ticker),
            _call_tool(mcp_tools, "get_latest_filing_summary", ticker=ticker, form_type="10-K"),
            _call_tool(mcp_tools, "get_technical_indicators", ticker=ticker),
        )

        news_data, news_ok, _ = results[0]
        quote_data, quote_ok, _ = results[1]
        fundamentals_data, fundamentals_ok, _ = results[2]
        filing_data, filing_ok, _ = results[3]
        indicators_data, indicators_ok, _ = results[4]

        # Track gaps
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
