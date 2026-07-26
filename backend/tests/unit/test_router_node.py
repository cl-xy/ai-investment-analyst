"""Unit tests for the router node."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage


@pytest.fixture
def base_state():
    return {
        "messages": [HumanMessage(content="Analyze NVDA and AAPL for me")],
        "intent": None,
        "tickers_to_analyze": [],
        "portfolio": [],
        "ticker_analyses": {},
        "raw_news": {},
        "raw_prices": {},
        "raw_filings": {},
        "report_markdown": "",
        "current_ticker": None,
        "error": None,
    }


@pytest.mark.asyncio
async def test_router_skips_llm_when_intent_preset(base_state):
    """If the caller pre-sets intent, router should return without calling the LLM."""
    base_state["intent"] = "list_portfolio"
    from src.agent.nodes.router import router_node

    mock_llm = AsyncMock()
    with patch("src.agent.nodes.router._get_llm", return_value=mock_llm):
        result = await router_node(base_state)

    mock_llm.ainvoke.assert_not_called()
    assert result == {}


@pytest.mark.asyncio
async def test_router_parses_single_ticker_intent(base_state):
    mock_response = MagicMock()
    mock_response.content = '{"intent": "single_ticker", "tickers": ["NVDA", "AAPL"], "reasoning": "User wants analysis"}'

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("src.agent.nodes.router._get_llm", return_value=mock_llm):
        from src.agent.nodes.router import router_node

        result = await router_node(base_state)

    assert result["intent"] == "single_ticker"
    assert result["tickers_to_analyze"] == ["NVDA", "AAPL"]


@pytest.mark.asyncio
async def test_router_parses_json_with_code_fences(base_state):
    """Router should correctly handle JSON via fallback extraction."""
    mock_response = MagicMock()
    mock_response.content = '```json\n{"intent": "full_report", "tickers": []}\n```'

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("src.agent.nodes.router._get_llm", return_value=mock_llm):
        from src.agent.nodes.router import router_node

        result = await router_node(base_state)

    assert result["intent"] == "full_report"
    assert result["tickers_to_analyze"] == []


@pytest.mark.asyncio
async def test_router_falls_back_to_conversational_on_bad_json(base_state):
    mock_response = MagicMock()
    mock_response.content = "I cannot determine the intent."

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("src.agent.nodes.router._get_llm", return_value=mock_llm):
        from src.agent.nodes.router import router_node

        result = await router_node(base_state)

    assert result["intent"] == "conversational"
    assert result["tickers_to_analyze"] == []
