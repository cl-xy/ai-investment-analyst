"""Unit tests for technical indicator calculations."""

import pytest
from src.mcp_servers.market_server.indicators import (
    compute_indicators,
    compute_macd,
    compute_rsi,
)


def _prices(values: list[float]) -> list[dict]:
    return [{"close": v} for v in values]


class TestRSI:
    def test_rsi_returns_none_for_insufficient_data(self):
        assert compute_rsi([100.0] * 10, period=14) is None

    def test_rsi_100_for_all_gains(self):
        closes = [float(i) for i in range(1, 30)]  # monotonically increasing
        rsi = compute_rsi(closes, 14)
        assert rsi == 100.0

    def test_rsi_in_valid_range(self):
        import random
        random.seed(42)
        closes = [100.0 + random.uniform(-5, 5) for _ in range(50)]
        rsi = compute_rsi(closes, 14)
        assert rsi is not None
        assert 0.0 <= rsi <= 100.0

    def test_rsi_overbought_signal(self):
        # Strongly trending up → RSI should be high
        closes = [100.0 + i * 2 for i in range(30)]
        rsi = compute_rsi(closes, 14)
        assert rsi is not None
        assert rsi > 70


class TestMACD:
    def test_macd_returns_none_for_insufficient_data(self):
        closes = [100.0] * 30  # need at least slow + signal = 35
        assert compute_macd(closes) is None

    def test_macd_returns_dict_with_required_keys(self):
        closes = [100.0 + i * 0.5 for i in range(50)]
        result = compute_macd(closes)
        assert result is not None
        assert "macd_line" in result
        assert "signal_line" in result
        assert "histogram" in result

    def test_macd_histogram_equals_line_minus_signal(self):
        closes = [100.0 + i * 0.3 for i in range(60)]
        result = compute_macd(closes)
        assert result is not None
        expected = round(result["macd_line"] - result["signal_line"], 4)
        assert abs(result["histogram"] - expected) < 0.0001


class TestComputeIndicators:
    def test_returns_none_fields_for_short_history(self):
        history = _prices([100.0] * 10)
        result = compute_indicators(history)
        assert result["rsi_14"] is None
        assert result["sma_50"] is None
        assert result["sma_200"] is None
        assert result["macd"] is None

    def test_sma_50_correct(self):
        closes = [float(i) for i in range(1, 61)]  # 1..60
        result = compute_indicators(_prices(closes))
        expected_sma50 = sum(range(11, 61)) / 50  # last 50 values: 11..60
        assert result["sma_50"] == round(expected_sma50, 4)

    def test_full_year_history_returns_all_fields(self):
        import random
        random.seed(0)
        closes = [150.0 + random.uniform(-10, 10) for _ in range(252)]
        result = compute_indicators(_prices(closes))
        assert result["rsi_14"] is not None
        assert result["sma_50"] is not None
        assert result["sma_200"] is not None
        assert result["macd"] is not None
