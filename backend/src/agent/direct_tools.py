"""
Direct in-process tool loading. Bypasses subprocess MCP servers by importing
the tool functions directly and wrapping them as LangChain StructuredTools.
Used in production where subprocess spawning is unreliable (Docker/Fly.io).
"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

# Explicit bounded thread pool for sync tool calls.
# Default pool is min(32, cpu_count+4) which can be as low as 5 on Fly.io shared-cpu-1x.
# 16 workers handles 3 concurrent analyses × 5 tools comfortably without exhaustion.
_TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=16, thread_name_prefix="mcp-tool")


# --- Schemas for tool arguments ---


class TickerInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol")


class PriceHistoryInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol")
    period: str = Field(default="3mo", description="Time period (1mo, 3mo, 6mo, 1y)")


class NewsInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol")
    days_back: int = Field(default=7, description="How many days back to search")
    max_articles: int = Field(default=10, description="Maximum articles to return")


class HeadlinesInput(BaseModel):
    category: str = Field(default="business", description="News category")
    limit: int = Field(default=20, description="Maximum headlines")


class SECInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol")
    form_type: str = Field(default="10-K", description="SEC form type")
    count: int = Field(default=3, description="Number of filings to return")


class SECSummaryInput(BaseModel):
    ticker: str = Field(description="Stock ticker symbol")
    form_type: str = Field(default="10-K", description="SEC form type")


class PortfolioPricesInput(BaseModel):
    prices: dict = Field(description="Dict of ticker to current price")


class AddPositionInput(BaseModel):
    ticker: str
    shares: float
    cost_basis: float
    sector: str = "Unknown"


class UpdatePositionInput(BaseModel):
    ticker: str
    shares: float | None = None
    cost_basis: float | None = None


def _wrap_sync(fn, **kwargs) -> str:
    """Call a sync function and return JSON string (MCP content-block format).

    Exceptions propagate to the caller so fetch_data can detect failures
    and avoid caching error responses.
    """
    result = fn(**kwargs)
    return json.dumps(result, default=str)


async def _wrap_async(fn, **kwargs) -> str:
    """Call an async function and return JSON string.

    Exceptions propagate to the caller so fetch_data can detect failures
    and avoid caching error responses.
    """
    result = await fn(**kwargs)
    return json.dumps(result, default=str)


async def _run_in_pool(fn, **kwargs) -> str:
    """Run a sync tool function in the bounded thread pool.

    Uses _TOOL_EXECUTOR (16 workers) instead of the default executor which
    can be as low as 5 threads on single-CPU deployments (Fly.io shared-cpu-1x).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_TOOL_EXECUTOR, partial(_wrap_sync, fn, **kwargs))


def _make_sync_tool(
    fn,
    name: str,
    description: str,
    args_schema: type[BaseModel] | None = None,
) -> StructuredTool:
    """Factory for creating a StructuredTool that runs a sync function in the thread pool."""

    def _sync(*args, **kwargs):
        return _wrap_sync(fn, **kwargs)

    async def _async(*args, **kwargs):
        return await _run_in_pool(fn, **kwargs)

    return StructuredTool.from_function(
        func=_sync,
        coroutine=_async,
        name=name,
        description=description,
        args_schema=args_schema,
    )


def _make_async_tool(
    fn,
    name: str,
    description: str,
    args_schema: type[BaseModel] | None = None,
) -> StructuredTool:
    """Factory for creating a StructuredTool that wraps an async function."""

    def _sync(*args, **kwargs):
        return json.dumps([])

    async def _async(*args, **kwargs):
        return await _wrap_async(fn, **kwargs)

    return StructuredTool.from_function(
        func=_sync,
        coroutine=_async,
        name=name,
        description=description,
        args_schema=args_schema,
    )


def load_direct_tools() -> dict:
    """
    Import MCP server modules directly and create LangChain StructuredTools.
    Returns dict of {tool_name: StructuredTool}.
    """
    tools = {}

    # --- Market tools ---
    try:
        from src.mcp_servers.market_server.server import (
            get_fundamentals,
            get_price_history,
            get_quote,
            get_technical_indicators,
        )

        tools["get_quote"] = _make_sync_tool(
            get_quote,
            name="get_quote",
            description="Get current market quote for a ticker. Returns current_price, change_pct, volume, market_cap, pe_ratio.",
            args_schema=TickerInput,
        )
        tools["get_fundamentals"] = _make_sync_tool(
            get_fundamentals,
            name="get_fundamentals",
            description="Get fundamental financial data for a ticker. Returns revenue, eps, debt_to_equity, profit_margin, etc.",
            args_schema=TickerInput,
        )
        tools["get_price_history"] = _make_sync_tool(
            get_price_history,
            name="get_price_history",
            description="Get historical price data for a ticker over a given period.",
            args_schema=PriceHistoryInput,
        )
        tools["get_technical_indicators"] = _make_sync_tool(
            get_technical_indicators,
            name="get_technical_indicators",
            description="Get technical indicators (RSI, MACD, moving averages) for a ticker.",
            args_schema=TickerInput,
        )
    except Exception as e:
        print(f"[direct_tools] Failed to load market tools: {e}")

    # --- News tools ---
    try:
        from src.mcp_servers.news_server.server import get_market_headlines, get_ticker_news

        tools["get_ticker_news"] = _make_sync_tool(
            get_ticker_news,
            name="get_ticker_news",
            description="Get recent news articles for a specific ticker.",
            args_schema=NewsInput,
        )
        tools["get_market_headlines"] = _make_sync_tool(
            get_market_headlines,
            name="get_market_headlines",
            description="Get current market news headlines.",
            args_schema=HeadlinesInput,
        )
    except Exception as e:
        print(f"[direct_tools] Failed to load news tools: {e}")

    # --- SEC tools ---
    try:
        from src.mcp_servers.sec_server.server import get_latest_filing_summary, search_sec_filings

        tools["search_sec_filings"] = _make_sync_tool(
            search_sec_filings,
            name="search_sec_filings",
            description="Search SEC EDGAR for filings by ticker and form type.",
            args_schema=SECInput,
        )
        tools["get_latest_filing_summary"] = _make_sync_tool(
            get_latest_filing_summary,
            name="get_latest_filing_summary",
            description="Get a summary of the latest SEC filing for a ticker.",
            args_schema=SECSummaryInput,
        )
    except Exception as e:
        print(f"[direct_tools] Failed to load SEC tools: {e}")

    # --- Portfolio tools ---
    try:
        from src.mcp_servers.portfolio_server.server import (
            add_position,
            get_portfolio,
            get_portfolio_value,
            remove_position,
            update_position,
        )

        tools["get_portfolio"] = _make_async_tool(
            get_portfolio,
            name="get_portfolio",
            description="Get all positions in the portfolio.",
        )
        tools["add_position"] = _make_async_tool(
            add_position,
            name="add_position",
            description="Add a new position to the portfolio.",
            args_schema=AddPositionInput,
        )
        tools["remove_position"] = _make_async_tool(
            remove_position,
            name="remove_position",
            description="Remove a position from the portfolio.",
            args_schema=TickerInput,
        )
        tools["update_position"] = _make_async_tool(
            update_position,
            name="update_position",
            description="Update shares or cost basis for a position.",
            args_schema=UpdatePositionInput,
        )
        tools["get_portfolio_value"] = _make_async_tool(
            get_portfolio_value,
            name="get_portfolio_value",
            description="Calculate total portfolio value given current prices.",
            args_schema=PortfolioPricesInput,
        )
    except Exception as e:
        print(f"[direct_tools] Failed to load portfolio tools: {e}")

    return tools
