"""Pure-Python technical indicator calculations from OHLCV data."""

from __future__ import annotations


def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 4)


def _ema(closes: list[float], period: int) -> list[float]:
    """Return a list of EMA values (same length as closes, None-padded at the start)."""
    if len(closes) < period:
        return []
    k = 2 / (period + 1)
    emas: list[float] = []
    seed = sum(closes[:period]) / period
    emas.append(seed)
    for price in closes[period:]:
        emas.append(price * k + emas[-1] * (1 - k))
    return emas


def compute_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def compute_macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict | None:
    """Return {macd_line, signal_line, histogram} or None if insufficient data."""
    if len(closes) < slow + signal:
        return None
    fast_emas = _ema(closes, fast)
    slow_emas = _ema(closes, slow)
    # Align lengths — slow EMA starts later
    offset = slow - fast
    macd_line = [f - s for f, s in zip(fast_emas[offset:], slow_emas)]
    if len(macd_line) < signal:
        return None
    signal_emas = _ema(macd_line, signal)
    if not signal_emas:
        return None
    macd_val = macd_line[-1]
    signal_val = signal_emas[-1]
    return {
        "macd_line": round(macd_val, 4),
        "signal_line": round(signal_val, 4),
        "histogram": round(macd_val - signal_val, 4),
    }


def compute_indicators(price_history: list[dict]) -> dict:
    """
    Accept a list of OHLCV dicts (each with a 'close' key) and return
    {rsi_14, sma_50, sma_200, macd}.
    """
    closes = [row["close"] for row in price_history if "close" in row]
    return {
        "rsi_14": compute_rsi(closes, 14),
        "sma_50": _sma(closes, 50),
        "sma_200": _sma(closes, 200),
        "macd": compute_macd(closes),
    }
