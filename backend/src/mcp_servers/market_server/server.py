from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP

from .cache import _fundamentals_cache, _history_cache, _quote_cache
from .indicators import compute_indicators
from .sources import alpha_vantage_market as av
from .sources import yfinance_client as yf_client

mcp = FastMCP("market-server")


def _get_quote_cached(ticker: str) -> dict:
    key = ticker.upper()
    if key in _quote_cache:
        return _quote_cache[key]
    try:
        data = yf_client.get_quote(key)
    except Exception:
        data = av.get_quote(key) or {}
    _quote_cache[key] = data
    return data


def _get_fundamentals_cached(ticker: str) -> dict:
    key = ticker.upper()
    if key in _fundamentals_cache:
        return _fundamentals_cache[key]
    try:
        data = yf_client.get_fundamentals(key)
    except Exception:
        data = av.get_fundamentals(key) or {}
    _fundamentals_cache[key] = data
    return data


def _get_history_cached(ticker: str, period: str) -> list[dict]:
    cache_key = f"{ticker.upper()}:{period}"
    if cache_key in _history_cache:
        return _history_cache[cache_key]
    try:
        data = yf_client.get_price_history(ticker.upper(), period)
    except Exception:
        data = []
    _history_cache[cache_key] = data
    return data


@mcp.tool()
def get_quote(ticker: str) -> dict:
    """
    Get current market quote for a ticker.
    Returns current_price, change_pct, volume, market_cap, pe_ratio, fifty_two_week_high, fifty_two_week_low.
    """
    return _get_quote_cached(ticker)


@mcp.tool()
def get_fundamentals(ticker: str) -> dict:
    """
    Get fundamental financial data for a ticker.
    Returns revenue, eps, debt_to_equity, profit_margin, revenue_growth_yoy,
    analyst_target, dividend_yield, beta, sector, industry, description.
    """
    return _get_fundamentals_cached(ticker)


@mcp.tool()
def get_price_history(ticker: str, period: str = "3mo") -> list[dict]:
    """
    Get historical OHLCV price data. period options: 1mo, 3mo, 6mo, 1y, 2y.
    Returns list of {date, open, high, low, close, volume}.
    """
    return _get_history_cached(ticker, period)


@mcp.tool()
def get_technical_indicators(ticker: str) -> dict:
    """
    Compute technical indicators for a ticker using 1 year of daily price history.
    Returns {rsi_14, sma_50, sma_200, macd: {macd_line, signal_line, histogram}}.
    RSI > 70 = overbought, < 30 = oversold.
    MACD histogram > 0 = bullish momentum, < 0 = bearish.
    """
    history = _get_history_cached(ticker, "1y")
    return compute_indicators(history)


if __name__ == "__main__":
    mcp.run()
