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

# Global semaphore bounding concurrent tool calls across all analyses.
# Prevents overwhelming external APIs (SEC EDGAR ~10 req/s, yfinance, newsapi).
# With analysis_slot semaphore(3) × 5 tools × N tickers, this caps actual I/O.
_GLOBAL_TOOL_SEMAPHORE = asyncio.Semaphore(15)


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


def _is_error_response(data) -> bool:
    """Check if a response is an error dict that should not be treated as valid data."""
    return isinstance(data, dict) and "error" in data and len(data) <= 2


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
        unwrapped = _unwrap(raw)
        # Detect error dicts that slipped through as "successful" responses
        if _is_error_response(unwrapped):
            log.warning("tool_returned_error tool=%s error=%s", name, unwrapped.get("error"))
            return unwrapped, False, duration_ms
        return unwrapped, True, duration_ms
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
        # Atomically consume budget before making the actual API call.
        # This prevents the TOCTOU race where multiple concurrent cache misses
        # all pass a read-only budget check and then exceed the limit.
        from src.cache.budget import use_budget

        if not await use_budget(provider):
            raise RuntimeError(f"Budget exhausted for {provider}")

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
    except Exception as e:
        # Cache miss + fetch failure: don't retry raw call (budget already consumed
        # inside _fetch). Return the error as a failed result.
        duration_ms = int((time.monotonic() - start) * 1000)
        return {"error": str(e)}, False, duration_ms, False


async def fetch_data_node(state: InvestmentAnalystState, *, mcp_tools: dict) -> dict:
    tickers = state.get("tickers_to_analyze", [])
    log.info("fetch_data_node: tickers=%s, tools_count=%d", tickers, len(mcp_tools))
    if not tickers:
        return {}

    # Per-provider budget check: only degrade the provider that's exhausted
    budget_exhausted: set[str] = set()
    try:
        from src.cache.budget import check_budget

        newsapi_ok, groq_ok = await asyncio.gather(
            check_budget("newsapi"),
            check_budget("groq"),
        )
        if not newsapi_ok:
            budget_exhausted.add("newsapi")
        if not groq_ok:
            budget_exhausted.add("groq")
        log.info(
            "fetch_data_node: budget_exhausted=%s",
            budget_exhausted or "none",
        )
    except Exception as e:
        log.warning("budget_check_failed: %s", e)

    # Bound concurrent tool calls across all tickers (global limit across analyses)
    async def _bounded_tool_cached(
        tools: dict, provider: str, tool_name: str, ticker: str, tool_kwargs: dict
    ) -> tuple[dict | list, bool, int, bool]:
        async with _GLOBAL_TOOL_SEMAPHORE:
            return await _call_tool_cached(tools, provider, tool_name, ticker, tool_kwargs)

    async def fetch_one(ticker: str) -> tuple[str, list, dict, str, list[str]]:
        """Fetch all data for one ticker with caching. Returns per-ticker results + gaps."""
        gaps: list[str] = []
        from src.cache.manager import cache_manager as cm

        # Define tool calls with their provider mapping
        tool_calls = [
            ("newsapi", "get_ticker_news", {"ticker": ticker, "days_back": 7, "max_articles": 10}),
            ("yfinance", "get_quote", {"ticker": ticker}),
            ("yfinance", "get_fundamentals", {"ticker": ticker}),
            ("sec_edgar", "get_latest_filing_summary", {"ticker": ticker, "form_type": "10-K"}),
            ("yfinance", "get_technical_indicators", {"ticker": ticker}),
        ]

        results = []
        # Separate budget-exhausted providers (cache-only) from live fetches
        cache_only_coros = []
        live_coros = []
        indices_cache = []
        indices_live = []

        for i, (provider, tool_name, kwargs) in enumerate(tool_calls):
            if provider in budget_exhausted:
                indices_cache.append(i)
                cache_only_coros.append(cm.get_cached_only(provider, tool_name, ticker))
            else:
                indices_live.append(i)
                live_coros.append(
                    _bounded_tool_cached(mcp_tools, provider, tool_name, ticker, kwargs)
                )

        # Run all live fetches concurrently (bounded by _GLOBAL_TOOL_SEMAPHORE)
        cache_results, live_results = await asyncio.gather(
            asyncio.gather(*cache_only_coros) if cache_only_coros else asyncio.sleep(0),
            asyncio.gather(*live_coros) if live_coros else asyncio.sleep(0),
        )
        if not cache_only_coros:
            cache_results = []
        if not live_coros:
            live_results = []

        # Merge results back in original order
        results = [None] * len(tool_calls)
        for idx, (i, (provider, tool_name, _kwargs)) in enumerate(
            zip(indices_cache, [tool_calls[j] for j in indices_cache])
        ):
            data, source_id, hit = cache_results[idx]
            if hit:
                results[i] = (data, True, 0, True)
            else:
                gaps.append(f"{tool_name} unavailable for {ticker} (budget exhausted)")
                results[i] = ({} if "news" not in tool_name else [], False, 0, False)

        for idx, i in enumerate(indices_live):
            results[i] = live_results[idx]

        news_data, news_ok, _, _ = results[0]
        quote_data, quote_ok, _, _ = results[1]
        fundamentals_data, fundamentals_ok, _, _ = results[2]
        filing_data, filing_ok, _, _ = results[3]
        indicators_data, indicators_ok, _, _ = results[4]

        # DEBUG
        print(f"[DEBUG] fetch_one {ticker}: quote type={type(quote_data).__name__} ok={quote_ok} val={str(quote_data)[:150]}", flush=True)
        print(f"[DEBUG] fetch_one {ticker}: news type={type(news_data).__name__} ok={news_ok} len={len(news_data) if isinstance(news_data, list) else 'N/A'}", flush=True)
        print(f"[DEBUG] fetch_one {ticker}: fund type={type(fundamentals_data).__name__} ok={fundamentals_ok}", flush=True)
        print(f"[DEBUG] fetch_one {ticker}: indicators type={type(indicators_data).__name__} ok={indicators_ok}", flush=True)
        print(f"[DEBUG] fetch_one {ticker}: filing type={type(filing_data).__name__} ok={filing_ok}", flush=True)

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

    all_results = await asyncio.gather(
        *[fetch_one(t) for t in tickers], return_exceptions=True
    )

    raw_news = {}
    raw_prices = {}
    raw_filings = {}
    all_gaps: list[str] = []

    for i, result in enumerate(all_results):
        ticker = tickers[i]
        if isinstance(result, BaseException):
            log.error("fetch_one_failed ticker=%s error=%s", ticker, result)
            all_gaps.append(f"All data unavailable for {ticker} (fetch error)")
            raw_news[ticker] = []
            raw_prices[ticker] = {"quote": {}, "fundamentals": {}, "indicators": {}}
            raw_filings[ticker] = ""
            continue
        _, news, prices, filing_text, gaps = result
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
