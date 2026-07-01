"""Unit tests for the portfolio_ops node."""

import pytest
from langchain_core.messages import HumanMessage
from unittest.mock import AsyncMock, MagicMock


def _make_state(intent: str, user_text: str, tickers: list[str] | None = None):
    return {
        "messages": [HumanMessage(content=user_text)],
        "intent": intent,
        "tickers_to_analyze": tickers or [],
        "portfolio": [],
        "ticker_analyses": {},
        "raw_news": {},
        "raw_prices": {},
        "raw_filings": {},
        "report_markdown": "",
        "current_ticker": None,
        "error": None,
    }


def _tool_response(data: dict | list) -> list[dict]:
    """Simulate the content-block format returned by LangChain MCP tools."""
    import json
    return [{"type": "text", "text": json.dumps(data)}]


def _make_tool(return_value):
    """Create a mock MCP tool whose .ainvoke() returns the given value."""
    tool = MagicMock()
    tool.ainvoke = AsyncMock(return_value=return_value)
    return tool


@pytest.mark.asyncio
async def test_list_portfolio_empty():
    from src.agent.nodes.portfolio_ops import portfolio_ops_node

    mcp_tools = {"get_portfolio": _make_tool(_tool_response([]))}
    state = _make_state("list_portfolio", "Show me my portfolio")

    result = await portfolio_ops_node(state, mcp_tools=mcp_tools)

    assert "messages" in result
    assert "empty" in result["messages"][0].content.lower()


@pytest.mark.asyncio
async def test_list_portfolio_with_positions():
    from src.agent.nodes.portfolio_ops import portfolio_ops_node

    positions = [
        {"ticker": "NVDA", "shares": 10.0, "cost_basis": 400.0, "sector": "Technology"},
        {"ticker": "AAPL", "shares": 5.0, "cost_basis": 150.0, "sector": "Technology"},
    ]
    mcp_tools = {"get_portfolio": _make_tool(_tool_response(positions))}
    state = _make_state("list_portfolio", "Show my portfolio")

    result = await portfolio_ops_node(state, mcp_tools=mcp_tools)

    content = result["messages"][0].content
    assert "NVDA" in content
    assert "AAPL" in content


@pytest.mark.asyncio
async def test_add_position():
    from src.agent.nodes.portfolio_ops import portfolio_ops_node

    mcp_tools = {
        "add_position": _make_tool(_tool_response(
            {"success": True, "message": "Position NVDA saved (10 shares @ $400.00)"}
        ))
    }
    state = _make_state(
        "add_position",
        "Add 10 shares of NVDA at $400.00 per share to my portfolio (sector: Technology)",
        tickers=["NVDA"],
    )

    result = await portfolio_ops_node(state, mcp_tools=mcp_tools)

    mcp_tools["add_position"].ainvoke.assert_called_once()
    call_kwargs = mcp_tools["add_position"].ainvoke.call_args[0][0]
    assert call_kwargs["ticker"] == "NVDA"
    assert call_kwargs["shares"] == 10.0
    assert call_kwargs["cost_basis"] == 400.0
    assert "NVDA" in result["messages"][0].content


@pytest.mark.asyncio
async def test_remove_position():
    from src.agent.nodes.portfolio_ops import portfolio_ops_node

    mcp_tools = {
        "remove_position": _make_tool(_tool_response(
            {"success": True, "message": "NVDA removed from portfolio"}
        ))
    }
    state = _make_state("remove_position", "Remove NVDA from my portfolio", tickers=["NVDA"])

    result = await portfolio_ops_node(state, mcp_tools=mcp_tools)

    mcp_tools["remove_position"].ainvoke.assert_called_once_with({"ticker": "NVDA"})
    assert "NVDA" in result["messages"][0].content


@pytest.mark.asyncio
async def test_add_position_missing_ticker():
    from src.agent.nodes.portfolio_ops import portfolio_ops_node

    add_position = _make_tool(_tool_response({}))
    mcp_tools = {"add_position": add_position}
    state = _make_state("add_position", "Add some shares", tickers=[])

    result = await portfolio_ops_node(state, mcp_tools=mcp_tools)

    add_position.ainvoke.assert_not_called()
    assert "ticker" in result["messages"][0].content.lower()
