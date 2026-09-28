"""Tests for bounded, degradable narrative report synthesis."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.nodes.generate_report import generate_report_node


def _state():
    return {
        "ticker_analyses": {
            "MDB": {
                "ticker": "MDB",
                "signal": "hold",
                "confidence": "medium",
                "sentiment_score": 0.1,
                "thesis": "Growth is balanced by execution risk.",
                "risk_flags": ["Valuation"],
                "price_data": {"current_price": 250},
                "fundamentals": {"sector": "Technology"},
                "sec_notes": "A large raw filing excerpt that must not be sent to the report model.",
                "citations": [{"claim": "Large citation payload"}],
            }
        }
    }


@pytest.mark.asyncio
async def test_report_timeout_keeps_analysis_successful_with_fallback_report():
    with patch(
        "src.agent.nodes.generate_report.invoke_with_fallback",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError,
    ):
        result = await generate_report_node(_state())

    assert result["report_status"] == "timed_out"
    assert "MDB" in result["report_markdown"]
    assert "Signal Summary" in result["report_markdown"]


@pytest.mark.asyncio
async def test_report_prompt_excludes_large_evidence_payloads():
    response = SimpleNamespace(content="## Executive Summary\nComplete")
    with patch(
        "src.agent.nodes.generate_report.invoke_with_fallback",
        new_callable=AsyncMock,
        return_value=response,
    ) as invoke:
        result = await generate_report_node(_state())

    prompt = invoke.await_args.args[0][1].content
    assert result["report_status"] == "generated"
    assert "raw filing excerpt" not in prompt
    assert "Large citation payload" not in prompt
    assert '"ticker": "MDB"' in prompt
