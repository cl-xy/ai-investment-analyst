from dotenv import load_dotenv

load_dotenv()

import logging
import time

from fastmcp import FastMCP

from .cache import _earnings_cache, _fundamentals_cache, _history_cache, _quote_cache
from .indicators import compute_indicators
from .sources import alpha_vantage_market as av
from .sources import yfinance_client as yf_client

log = logging.getLogger(__name__)

mcp = FastMCP("market-server")

import concurrent.futures

_TIMEOUT = 30  # seconds
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _call_with_timeout(fn, *args):
    """Run a sync function in a thread with a timeout."""
    future = _EXECUTOR.submit(fn, *args)
    return future.result(timeout=_TIMEOUT)


def _call_with_retry(fn, *args, retries: int = 1, delay: float = 2.0):
    """Call fn with timeout, retrying on failure before falling back."""
    last_exc = None
    for attempt in range(1 + retries):
        try:
            return _call_with_timeout(fn, *args)
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                log.warning(
                    "market-server: %s(%s) attempt %d failed, retrying in %.1fs",
                    fn.__name__,
                    args,
                    attempt + 1,
                    delay,
                )
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _get_quote_cached(ticker: str) -> dict:
    key = ticker.upper()
    if key in _quote_cache:
        return _quote_cache[key]
    try:
        data = _call_with_retry(yf_client.get_quote, key)
    except Exception:
        try:
            data = av.get_quote(key) or {}
        except Exception:
            data = {}
    if data:
        _quote_cache[key] = data
    return data


def _get_fundamentals_cached(ticker: str) -> dict:
    key = ticker.upper()
    if key in _fundamentals_cache:
        return _fundamentals_cache[key]
    try:
        data = _call_with_retry(yf_client.get_fundamentals, key)
    except Exception:
        try:
            data = av.get_fundamentals(key) or {}
        except Exception:
            data = {}
    if data:
        _fundamentals_cache[key] = data
    return data


def _get_earnings_calendar_cached(ticker: str) -> dict:
    key = ticker.upper()
    if key in _earnings_cache:
        return _earnings_cache[key]
    try:
        data = _call_with_timeout(yf_client.get_earnings_calendar, key)
    except Exception:
        data = {}
    if data:
        _earnings_cache[key] = data
    return data


def _get_history_cached(ticker: str, period: str) -> list[dict]:
    cache_key = f"{ticker.upper()}:{period}"
    if cache_key in _history_cache:
        return _history_cache[cache_key]
    try:
        data = _call_with_timeout(yf_client.get_price_history, ticker.upper(), period)
    except Exception:
        data = []
    if data:
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
def get_earnings_calendar(ticker: str) -> dict:
    """
    Get the next earnings date for a ticker.
    Returns next_earnings_date, days_until_earnings, eps_estimate.
    Returns {} if no upcoming earnings date is known.
    """
    return _get_earnings_calendar_cached(ticker)


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
