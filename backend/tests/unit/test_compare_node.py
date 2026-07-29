"""Unit tests for the compare node."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.compare import compare_node


def _analysis(ticker, signal="buy", confidence="high", sentiment=0.5):
    return {
        "ticker": ticker,
        "signal": signal,
        "confidence": confidence,
        "sentiment_score": sentiment,
        "risk_flags": [],
        "news_summary": "",
    }


@pytest.fixture
def two_ticker_state():
    return {
        "ticker_analyses": {
            "NVDA": _analysis("NVDA", signal="buy"),
            "AAPL": _analysis("AAPL", signal="hold"),
        }
    }


@pytest.mark.asyncio
async def test_compare_node_skips_when_fewer_than_two_analyses():
    result = await compare_node({"ticker_analyses": {"NVDA": _analysis("NVDA")}})
    assert result == {}


@pytest.mark.asyncio
async def test_compare_node_uses_invoke_with_fallback(two_ticker_state):
    """The node should go through the hardened LLM path, not a bare ChatOpenAI client."""
    payload = {
        "tickers": ["NVDA", "AAPL"],
        "summary": "NVDA has stronger momentum.",
        "metrics_table": [],
        "relative_ranking": [],
        "key_differentiators": [],
    }
    mock_response = MagicMock()
    mock_response.content = json.dumps(payload)

    with patch(
        "src.agent.nodes.compare.invoke_with_fallback", new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = mock_response
        result = await compare_node(two_ticker_state)

    mock_invoke.assert_awaited_once()
    assert result["comparison"]["status"] == "ok"
    assert result["comparison"]["summary"] == "NVDA has stronger momentum."


@pytest.mark.asyncio
async def test_compare_node_surfaces_failure_instead_of_dropping_it(two_ticker_state):
    """On any failure (both models down), status should be 'failed', not a silently empty dict."""
    with patch(
        "src.agent.nodes.compare.invoke_with_fallback", new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.side_effect = RuntimeError("both primary and fallback models failed")
        result = await compare_node(two_ticker_state)

    assert "comparison" in result
    assert result["comparison"]["status"] == "failed"
    assert "both primary and fallback" in result["comparison"]["error"]


@pytest.mark.asyncio
async def test_compare_node_surfaces_failure_on_invalid_json(two_ticker_state):
    """A response that fails Pydantic validation should also degrade to status=failed."""
    mock_response = MagicMock()
    mock_response.content = "not valid json"

    with patch(
        "src.agent.nodes.compare.invoke_with_fallback", new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = mock_response
        result = await compare_node(two_ticker_state)

    assert result["comparison"]["status"] == "failed"
