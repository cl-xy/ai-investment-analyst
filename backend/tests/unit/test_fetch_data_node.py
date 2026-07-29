"""Unit tests for the fetch_data node."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage


def _text_block(data) -> list[dict]:
    return [{"type": "text", "text": json.dumps(data)}]


@pytest.fixture
def base_state():
    return {
        "messages": [HumanMessage(content="Analyze NVDA")],
        "intent": "single_ticker",
        "tickers_to_analyze": ["NVDA"],
        "portfolio": [],
        "ticker_analyses": {},
        "raw_news": {},
        "raw_prices": {},
        "raw_filings": {},
        "data_gaps": [],
        "report_markdown": "",
        "current_ticker": None,
        "error": None,
    }


def _make_tool(return_value):
    """Create a mock MCP tool whose .ainvoke() returns the given value."""
    tool = MagicMock()
    tool.ainvoke = AsyncMock(return_value=return_value)
    return tool


def _mock_cache_passthrough():
    """Mock cache_manager.get_or_fetch to always call the fetch function directly."""

    async def _passthrough(provider, tool, ticker, fetch_fn):
        data = await fetch_fn()
        return data, f"{provider}:{ticker}:mock", False

    return _passthrough


@pytest.mark.asyncio
@patch("src.agent.nodes.fetch_data.cache_manager")
@patch("src.cache.budget.check_budget", new_callable=AsyncMock, return_value=True)
@patch("src.cache.budget.use_budget", new_callable=AsyncMock, return_value=True)
async def test_fetch_data_populates_all_fields(mock_use, mock_check, mock_cache, base_state):
    mock_cache.get_or_fetch = AsyncMock(side_effect=_mock_cache_passthrough())

    from src.agent.nodes.fetch_data import fetch_data_node

    mock_news = [
        {
            "title": "NVDA surges",
            "source": "Bloomberg",
            "snippet": "Big gains",
            "published_at": "2024-01-10",
            "url": "http://example.com",
        }
    ]
    mock_quote = {"ticker": "NVDA", "price": 500.0, "change_pct": 2.5}
    mock_fundamentals = {"eps_ttm": 12.5, "sector": "Technology"}
    mock_filing = {"text_excerpt": "Risk factors include..."}
    mock_indicators = {"rsi_14": 65.0, "sma_50": 480.0, "sma_200": 420.0, "macd": None}
    mock_earnings = {"next_earnings_date": "2026-08-15", "days_until_earnings": 17}

    mcp_tools = {
        "get_ticker_news": _make_tool(_text_block(mock_news)),
        "get_quote": _make_tool(_text_block(mock_quote)),
        "get_fundamentals": _make_tool(_text_block(mock_fundamentals)),
        "get_latest_filing_summary": _make_tool(_text_block(mock_filing)),
        "get_technical_indicators": _make_tool(_text_block(mock_indicators)),
        "get_earnings_calendar": _make_tool(_text_block(mock_earnings)),
    }

    result = await fetch_data_node(base_state, mcp_tools=mcp_tools)

    assert "NVDA" in result["raw_news"]
    assert result["raw_news"]["NVDA"][0]["title"] == "NVDA surges"

    assert "NVDA" in result["raw_prices"]
    assert result["raw_prices"]["NVDA"]["quote"]["price"] == 500.0
    assert result["raw_prices"]["NVDA"]["fundamentals"]["sector"] == "Technology"
    assert result["raw_prices"]["NVDA"]["indicators"]["rsi_14"] == 65.0

    assert result["raw_filings"]["NVDA"] == "Risk factors include..."

    assert result["raw_earnings"]["NVDA"]["next_earnings_date"] == "2026-08-15"
    assert result["raw_earnings"]["NVDA"]["days_until_earnings"] == 17


@pytest.mark.asyncio
@patch("src.agent.nodes.fetch_data.cache_manager")
@patch("src.cache.budget.check_budget", new_callable=AsyncMock, return_value=True)
@patch("src.cache.budget.use_budget", new_callable=AsyncMock, return_value=True)
async def test_fetch_data_missing_earnings_tool_is_not_a_data_gap(
    mock_use, mock_check, mock_cache, base_state
):
    """Most tickers have no confirmed upcoming earnings date — that's not
    a failure worth surfacing to the user as a data gap."""
    mock_cache.get_or_fetch = AsyncMock(side_effect=_mock_cache_passthrough())

    from src.agent.nodes.fetch_data import fetch_data_node

    mcp_tools = {
        "get_ticker_news": _make_tool(_text_block([])),
        "get_quote": _make_tool(_text_block({})),
        "get_fundamentals": _make_tool(_text_block({})),
        "get_latest_filing_summary": _make_tool(_text_block({})),
        "get_technical_indicators": _make_tool(_text_block({})),
        # Note: no "get_earnings_calendar" tool registered at all.
    }

    result = await fetch_data_node(base_state, mcp_tools=mcp_tools)

    assert result["raw_earnings"]["NVDA"] == {}
    assert not any("earnings" in gap.lower() for gap in result["data_gaps"])


@pytest.mark.asyncio
@patch("src.agent.nodes.fetch_data.cache_manager")
@patch("src.cache.budget.check_budget", new_callable=AsyncMock, return_value=True)
@patch("src.cache.budget.use_budget", new_callable=AsyncMock, return_value=True)
async def test_fetch_data_handles_tool_errors_gracefully(mock_use, mock_check, mock_cache, base_state):
    # Make cache passthrough that will hit the failing tools
    async def _failing_passthrough(provider, tool, ticker, fetch_fn):
        try:
            data = await fetch_fn()
            return data, f"{provider}:{ticker}:mock", False
        except Exception:
            raise

    mock_cache.get_or_fetch = AsyncMock(side_effect=_failing_passthrough)

    from src.agent.nodes.fetch_data import fetch_data_node

    failing_tool = MagicMock()
    failing_tool.ainvoke = AsyncMock(side_effect=Exception("Network error"))
    mcp_tools = {
        "get_ticker_news": failing_tool,
        "get_quote": failing_tool,
        "get_fundamentals": failing_tool,
        "get_latest_filing_summary": failing_tool,
        "get_technical_indicators": failing_tool,
    }

    result = await fetch_data_node(base_state, mcp_tools=mcp_tools)

    # Should not raise — errors are captured
    assert result["raw_news"]["NVDA"] == []
    assert isinstance(result["raw_prices"]["NVDA"]["quote"], dict)
    assert result["raw_filings"]["NVDA"] == ""
    assert len(result["data_gaps"]) > 0


@pytest.mark.asyncio
async def test_fetch_data_returns_empty_for_no_tickers(base_state):
    from src.agent.nodes.fetch_data import fetch_data_node

    base_state["tickers_to_analyze"] = []
    result = await fetch_data_node(base_state, mcp_tools={})
    assert result == {}


@pytest.mark.asyncio
@patch("src.agent.nodes.fetch_data.cache_manager")
@patch("src.cache.budget.check_budget", new_callable=AsyncMock, return_value=True)
@patch("src.cache.budget.use_budget", new_callable=AsyncMock, return_value=True)
async def test_fetch_data_fetches_multiple_tickers_in_parallel(mock_use, mock_check, mock_cache, base_state):
    mock_cache.get_or_fetch = AsyncMock(side_effect=_mock_cache_passthrough())

    from src.agent.nodes.fetch_data import fetch_data_node

    base_state["tickers_to_analyze"] = ["NVDA", "AAPL"]

    call_counts = {"count": 0}

    async def fake_news_ainvoke(kwargs):
        call_counts["count"] += 1
        return _text_block([])

    news_tool = MagicMock()
    news_tool.ainvoke = AsyncMock(side_effect=fake_news_ainvoke)

    mcp_tools = {
        "get_ticker_news": news_tool,
        "get_quote": _make_tool(_text_block({})),
        "get_fundamentals": _make_tool(_text_block({})),
        "get_latest_filing_summary": _make_tool(_text_block({})),
        "get_technical_indicators": _make_tool(_text_block({})),
    }

    result = await fetch_data_node(base_state, mcp_tools=mcp_tools)

    assert "NVDA" in result["raw_prices"]
    assert "AAPL" in result["raw_prices"]
    assert call_counts["count"] == 2
