"""
Tests for Pydantic structured output schemas.
Validates that model outputs conform to the expected structure.
"""

import pytest
from pydantic import ValidationError

from src.agent.structured_output import AnalysisOutput, Citation, RouterOutput


class TestAnalysisOutput:
    def test_valid_analysis(self):
        data = {
            "ticker": "NVDA",
            "signal": "buy",
            "confidence": "high",
            "sentiment_score": 0.75,
            "thesis": "Strong AI demand driving revenue growth above expectations.",
            "bull_case": ["Data center revenue +150% YoY", "AI moat deepening"],
            "bear_case": ["Valuation stretched at 60x forward P/E", "China export risk"],
            "risk_flags": ["Concentration risk in AI segment"],
            "citations": [
                {"source_id": "yfinance:NVDA:1706140800", "claim": "Revenue +150% YoY", "provider": "yfinance"}
            ],
            "data_gaps": [],
            "price_data": {"price": 875.0},
            "fundamentals": {"pe_ratio": 60.2},
            "sec_notes": "10-K mentions AI demand inflection",
            "news_summary": "Positive sentiment driven by earnings beat",
        }
        output = AnalysisOutput(**data)
        assert output.ticker == "NVDA"
        assert output.signal == "buy"
        assert output.confidence == "high"
        assert len(output.citations) == 1

    def test_sentiment_score_bounds(self):
        # Valid: -1.0 to 1.0
        data = _minimal_analysis(sentiment_score=1.0)
        assert AnalysisOutput(**data).sentiment_score == 1.0

        data = _minimal_analysis(sentiment_score=-1.0)
        assert AnalysisOutput(**data).sentiment_score == -1.0

        # Invalid: out of bounds
        with pytest.raises(ValidationError):
            AnalysisOutput(**_minimal_analysis(sentiment_score=1.5))

        with pytest.raises(ValidationError):
            AnalysisOutput(**_minimal_analysis(sentiment_score=-2.0))

    def test_invalid_signal(self):
        with pytest.raises(ValidationError):
            AnalysisOutput(**_minimal_analysis(signal="strong_buy"))

    def test_invalid_confidence(self):
        with pytest.raises(ValidationError):
            AnalysisOutput(**_minimal_analysis(confidence="very_high"))

    def test_defaults_for_optional_fields(self):
        data = {
            "ticker": "AAPL",
            "signal": "hold",
            "confidence": "medium",
            "sentiment_score": 0.1,
            "thesis": "Stable but limited upside at current valuation.",
        }
        output = AnalysisOutput(**data)
        assert output.bull_case == []
        assert output.bear_case == []
        assert output.risk_flags == []
        assert output.citations == []
        assert output.data_gaps == []
        assert output.price_data == {}
        assert output.fundamentals == {}

    def test_insufficient_data_signal(self):
        data = _minimal_analysis(signal="insufficient_data", confidence="low")
        output = AnalysisOutput(**data)
        assert output.signal == "insufficient_data"


class TestCitation:
    def test_valid_citation(self):
        c = Citation(
            source_id="newsapi:NVDA:1706140800",
            claim="Positive earnings surprise",
            provider="newsapi",
        )
        assert c.provider == "newsapi"

    def test_citation_requires_all_fields(self):
        with pytest.raises(ValidationError):
            Citation(source_id="test", claim="test")  # type: ignore — missing provider


class TestRouterOutput:
    def test_valid_router_output(self):
        data = {
            "intent": "single_ticker",
            "tickers": ["NVDA"],
            "reasoning": "User asked to analyze NVDA",
        }
        output = RouterOutput(**data)
        assert output.intent == "single_ticker"
        assert output.tickers == ["NVDA"]

    def test_invalid_intent(self):
        with pytest.raises(ValidationError):
            RouterOutput(intent="unknown_intent", tickers=[])

    def test_defaults(self):
        output = RouterOutput(intent="conversational")
        assert output.tickers == []
        assert output.reasoning == ""


def _minimal_analysis(**overrides) -> dict:
    """Helper to create minimal valid analysis data with overrides."""
    base = {
        "ticker": "TEST",
        "signal": "hold",
        "confidence": "medium",
        "sentiment_score": 0.0,
        "thesis": "Test thesis.",
    }
    base.update(overrides)
    return base
