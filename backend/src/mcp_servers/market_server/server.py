from dotenv import load_dotenv

load_dotenv()

import concurrent.futures
import logging
import threading
import time

from fastmcp import FastMCP

from src.validation import validate_ticker

from .cache import _earnings_cache, _fundamentals_cache, _history_cache, _quote_cache
from .indicators import compute_indicators
from .sources import alpha_vantage_market as av
from .sources import yfinance_client as yf_client

log = logging.getLogger(__name__)

mcp = FastMCP("market-server")

_TIMEOUT = 30  # seconds
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# Lock protecting TTLCache operations (cachetools.TTLCache is not thread-safe;
# even reads can mutate internal state during expiry eviction).
_cache_lock = threading.Lock()

_VALID_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y"}


def _validate_ticker(ticker: str) -> str:
    """Normalize and validate ticker input. Returns uppercased ticker or raises ValueError."""
    return validate_ticker(ticker)


def _call_with_timeout(fn, *args):
    """Run a sync function in a thread with a timeout.

    Note: future.result(timeout=...) does not cancel the underlying thread.
    The bounded pool size (4) limits the leak; callers should set real HTTP
    timeouts inside the client libraries for true cancellation.
    """
    future = _EXECUTOR.submit(fn, *args)
    try:
        return future.result(timeout=_TIMEOUT)
    except concurrent.futures.TimeoutError:
        future.cancel()  # prevents queued (not-yet-started) work only
        raise


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
    key = _validate_ticker(ticker)
    with _cache_lock:
        if key in _quote_cache:
            return _quote_cache[key]
    try:
        data = _call_with_retry(yf_client.get_quote, key)
    except Exception:
        try:
            data = _call_with_timeout(av.get_quote, key) or {}
        except Exception:
            log.warning("market-server: all sources failed for quote %s", key)
            data = {}
    if data:
        with _cache_lock:
            _quote_cache[key] = data
    return data


def _get_fundamentals_cached(ticker: str) -> dict:
    key = _validate_ticker(ticker)
    with _cache_lock:
        if key in _fundamentals_cache:
            return _fundamentals_cache[key]
    try:
        data = _call_with_retry(yf_client.get_fundamentals, key)
    except Exception:
        try:
            data = _call_with_timeout(av.get_fundamentals, key) or {}
        except Exception:
            log.warning("market-server: all sources failed for fundamentals %s", key)
            data = {}
    if data:
        with _cache_lock:
            _fundamentals_cache[key] = data
    return data


def _get_earnings_calendar_cached(ticker: str) -> dict:
    key = _validate_ticker(ticker)
    with _cache_lock:
        if key in _earnings_cache:
            return _earnings_cache[key]
    try:
        data = _call_with_timeout(yf_client.get_earnings_calendar, key)
    except Exception:
        data = {}
    if data:
        with _cache_lock:
            _earnings_cache[key] = data
    return data


def _get_history_cached(ticker: str, period: str) -> list[dict]:
    key = _validate_ticker(ticker)
    if period not in _VALID_PERIODS:
        period = "3mo"  # fall back to default for invalid period
    cache_key = f"{key}:{period}"
    with _cache_lock:
        if cache_key in _history_cache:
            return _history_cache[cache_key]
    try:
        data = _call_with_timeout(yf_client.get_price_history, key, period)
    except Exception:
        data = []
    if data:
        with _cache_lock:
            _history_cache[cache_key] = data
    return data


@mcp.tool()
def get_quote(ticker: str) -> dict:
    """
    Get current market quote for a ticker.
    Returns current_price, change_pct, volume, market_cap, pe_ratio, fifty_two_week_high, fifty_two_week_low.
    """
    try:
        return _get_quote_cached(ticker)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def get_fundamentals(ticker: str) -> dict:
    """
    Get fundamental financial data for a ticker.
    Returns revenue, eps, debt_to_equity, profit_margin, revenue_growth_yoy,
    analyst_target, dividend_yield, beta, sector, industry, description.
    """
    try:
        return _get_fundamentals_cached(ticker)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def get_earnings_calendar(ticker: str) -> dict:
    """
    Get the next earnings date for a ticker.
    Returns next_earnings_date, days_until_earnings, eps_estimate.
    Returns {} if no upcoming earnings date is known.
    """
    try:
        return _get_earnings_calendar_cached(ticker)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def get_price_history(ticker: str, period: str = "3mo") -> list[dict]:
    """
    Get historical OHLCV price data. period options: 1mo, 3mo, 6mo, 1y, 2y.
    Returns list of {date, open, high, low, close, volume}.
    """
    try:
        return _get_history_cached(ticker, period)
    except ValueError as e:
        return [{"error": str(e)}]


@mcp.tool()
def get_technical_indicators(ticker: str) -> dict:
    """
    Compute technical indicators for a ticker using 1 year of daily price history.
    Returns {rsi_14, sma_50, sma_200, macd: {macd_line, signal_line, histogram}}.
    RSI > 70 = overbought, < 30 = oversold.
    MACD histogram > 0 = bullish momentum, < 0 = bearish.
    """
    try:
        history = _get_history_cached(ticker, "1y")
    except ValueError as e:
        return {"error": str(e)}
    return compute_indicators(history)


if __name__ == "__main__":
    mcp.run()
