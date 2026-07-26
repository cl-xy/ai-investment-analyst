"""Unit tests for the analyze_ticker node."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage


@pytest.fixture
def state_with_ticker_data():
    return {
        "messages": [HumanMessage(content="Analyze NVDA")],
        "intent": "single_ticker",
        "tickers_to_analyze": ["NVDA"],
        "portfolio": [],
        "ticker_analyses": {},
        "raw_news": {
            "NVDA": [
                {
                    "title": "NVDA beats earnings",
                    "source": "Reuters",
                    "snippet": "Strong quarter.",
                    "published_at": "2024-01-10",
                }
            ]
        },
        "raw_prices": {
            "NVDA": {
                "quote": {
                    "ticker": "NVDA",
                    "price": 500.0,
                    "change_pct": 2.5,
                    "market_cap": 1_200_000_000_000,
                },
                "fundamentals": {"eps_ttm": 12.5, "pe_ratio": 40, "sector": "Technology"},
                "indicators": {
                    "rsi_14": 62.3,
                    "sma_50": 480.0,
                    "sma_200": 420.0,
                    "macd": {"macd_line": 5.2, "signal_line": 4.1, "histogram": 1.1},
                },
            }
        },
        "raw_filings": {"NVDA": "Risk factors include supply chain constraints..."},
        "report_markdown": "",
        "current_ticker": None,
        "error": None,
    }


@pytest.mark.asyncio
async def test_analyze_ticker_returns_analysis(state_with_ticker_data):
    mock_response = MagicMock()
    mock_response.content = """{
        "ticker": "NVDA",
        "signal": "buy",
        "confidence": "high",
        "sentiment_score": 0.8,
        "thesis": "Strong earnings beat with positive guidance across all segments.",
        "bull_case": ["AI demand surge", "Data center growth"],
        "bear_case": ["High valuation", "Export restrictions"],
        "news_summary": "Strong earnings beat with positive guidance.",
        "risk_flags": ["Supply chain risk"],
        "citations": [],
        "data_gaps": [],
        "sec_notes": "Company highlights supply chain as primary risk."
    }"""

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("src.agent.nodes.analyze_ticker._get_llm", return_value=mock_llm):
        from src.agent.nodes.analyze_ticker import analyze_ticker_node

        result = await analyze_ticker_node(state_with_ticker_data)

    assert "ticker_analyses" in result
    analysis = result["ticker_analyses"]["NVDA"]
    assert analysis["signal"] == "buy"
    assert analysis["confidence"] == "high"
    assert analysis["sentiment_score"] == 0.8
    assert "Supply chain risk" in analysis["risk_flags"]
    assert result["current_ticker"] == "NVDA"


@pytest.mark.asyncio
async def test_analyze_ticker_handles_code_fenced_json(state_with_ticker_data):
    """Analyst node should handle JSON that fails Pydantic but succeeds via fallback."""
    mock_response = MagicMock()
    mock_response.content = """```json
{
    "ticker": "NVDA",
    "signal": "hold",
    "confidence": "medium",
    "sentiment_score": 0.2,
    "news_summary": "Mixed signals this week.",
    "risk_flags": [],
    "sec_notes": ""
}
```"""

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("src.agent.nodes.analyze_ticker._get_llm", return_value=mock_llm):
        from src.agent.nodes.analyze_ticker import analyze_ticker_node

        result = await analyze_ticker_node(state_with_ticker_data)

    assert result["ticker_analyses"]["NVDA"]["signal"] == "hold"


@pytest.mark.asyncio
async def test_analyze_ticker_falls_back_on_invalid_json(state_with_ticker_data):
    """Node should produce an insufficient_data fallback if the LLM returns garbage."""
    mock_response = MagicMock()
    mock_response.content = "I cannot analyze this stock right now."

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch("src.agent.nodes.analyze_ticker._get_llm", return_value=mock_llm):
        from src.agent.nodes.analyze_ticker import analyze_ticker_node

        result = await analyze_ticker_node(state_with_ticker_data)

    analysis = result["ticker_analyses"]["NVDA"]
    assert analysis["signal"] == "insufficient_data"
    assert "Analysis parsing error" in analysis["risk_flags"]


@pytest.mark.asyncio
async def test_analyze_ticker_skips_already_analyzed(state_with_ticker_data):
    """Node should skip tickers that are already in ticker_analyses."""
    state_with_ticker_data["ticker_analyses"] = {
        "NVDA": {
            "ticker": "NVDA",
            "signal": "buy",
            "confidence": "high",
            "sentiment_score": 0.9,
            "news_summary": "Already done.",
            "risk_flags": [],
            "price_data": {},
            "fundamentals": {},
            "sec_notes": "",
        }
    }

    mock_llm = AsyncMock()

    with patch("src.agent.nodes.analyze_ticker._get_llm", return_value=mock_llm):
        from src.agent.nodes.analyze_ticker import analyze_ticker_node

        result = await analyze_ticker_node(state_with_ticker_data)

    mock_llm.ainvoke.assert_not_called()
    assert result == {}
