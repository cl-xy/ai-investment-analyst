"""
Tests for input validation on the streaming endpoint.
"""

import re

import pytest

VALID_PATTERN = re.compile(r"\A[A-Z0-9.]{1,10}\Z")


class TestTickerValidation:
    """Test the ticker validation regex used in the stream endpoint."""

    @pytest.mark.parametrize(
        "ticker",
        [
            "NVDA",
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "META",
            "SPY",
            "BRK.B",
            "BRK.A",
            "V",
            "A",  # Single char and dots
            "VOO",
            "QQQ",
            "IWM",  # ETFs
        ],
    )
    def test_valid_tickers(self, ticker):
        assert VALID_PATTERN.match(ticker)

    @pytest.mark.parametrize(
        "ticker",
        [
            "",
            " ",
            "TOOLONGTICKER",
            "nvda",  # lowercase
            "NV DA",
            "NVDA!",
            "NVDA@",
            "$NVDA",  # special chars
            "NVDA\n",
            "NVDA\t",
            "../etc",  # injection attempts
            "A" * 11,  # too long
        ],
    )
    def test_invalid_tickers(self, ticker):
        assert not VALID_PATTERN.match(ticker)

    def test_ticker_normalization(self):
        """Tickers should be uppercased and stripped."""
        raw = ["nvda", " aapl ", "MSFT", "  googl"]
        normalized = [t.strip().upper() for t in raw if t.strip()]
        assert normalized == ["NVDA", "AAPL", "MSFT", "GOOGL"]

    def test_deduplication(self):
        """Duplicate tickers should be removed."""
        raw = ["NVDA", "AAPL", "nvda", "NVDA"]
        seen = set()
        result = []
        for t in raw:
            upper = t.upper().strip()
            if upper not in seen:
                seen.add(upper)
                result.append(upper)
        assert result == ["NVDA", "AAPL"]
