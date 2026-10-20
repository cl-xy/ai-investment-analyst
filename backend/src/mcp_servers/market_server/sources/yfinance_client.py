import logging
import math
import random
import time
from datetime import date as _date

import yfinance as yf
from yfinance.exceptions import YFRateLimitError

log = logging.getLogger(__name__)


def _ticker(symbol: str) -> yf.Ticker:
    """Create a Ticker on yfinance's own session.

    I used to pass a plain requests.Session here to enforce a timeout. That
    bypassed yfinance's curl_cffi browser-impersonating session, and Yahoo
    started answering every call (crumb included) with 429 from the Fly IP.
    On the same machine the default session returned data. The overall time
    budget is still enforced by the thread timeout in server.py.
    """
    return yf.Ticker(symbol)


# Yahoo throttles the shared Fly.io IP in bursts. A short backoff usually clears
# it, so retry a couple of times before giving up. Keep the total sleep small:
# the caller's 30s deadline covers the whole fallback chain.
_RATE_LIMIT_RETRIES = 2
_RATE_LIMIT_BASE_DELAY = 1.5


def _is_rate_limited(exc: Exception) -> bool:
    return isinstance(exc, YFRateLimitError) or "too many requests" in str(exc).lower()


def _retry_on_rate_limit(fn, *, label: str):
    """Call fn(), retrying with jittered backoff only when Yahoo rate limits us."""
    for attempt in range(_RATE_LIMIT_RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            if not _is_rate_limited(e) or attempt == _RATE_LIMIT_RETRIES:
                raise
            delay = _RATE_LIMIT_BASE_DELAY * (attempt + 1) + random.uniform(0, 0.5)
            log.warning(
                "yfinance_rate_limited %s attempt=%d retry_in=%.1fs", label, attempt + 1, delay
            )
            time.sleep(delay)


def _download_fallback(ticker: str) -> dict:
    """
    Last-resort price fetch using yf.download() which hits Yahoo's chart/v8 API.
    This endpoint is more permissive with geo/IP restrictions than quoteSummary.
    Returns a minimal quote dict or raises ValueError.
    """
    try:
        df = yf.download(ticker, period="5d", progress=False, timeout=20)
        if df.empty:
            raise ValueError("download returned empty dataframe")
        # Handle multi-level columns from yf.download
        if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
            # MultiIndex: ('Close', 'WIX') etc
            close_col = ("Close", ticker.upper())
            vol_col = ("Volume", ticker.upper())
            price = round(float(df[close_col].iloc[-1]), 4)
            prev_close = round(float(df[close_col].iloc[-2]), 4) if len(df) >= 2 else None
            volume = int(df[vol_col].iloc[-1]) if vol_col in df.columns else None
        else:
            price = round(float(df["Close"].iloc[-1]), 4)
            prev_close = round(float(df["Close"].iloc[-2]), 4) if len(df) >= 2 else None
            volume = int(df["Volume"].iloc[-1]) if "Volume" in df.columns else None

        change_pct = None
        if prev_close is not None and prev_close != 0:
            change_pct = round((price - prev_close) / prev_close * 100, 2)

        log.info("download_fallback_success ticker=%s price=%s", ticker, price)
        return {
            "ticker": ticker.upper(),
            "current_price": price,
            "change_pct": change_pct,
            "volume": volume,
            "market_cap": None,
            "pe_ratio": None,
            "fifty_two_week_high": None,
            "fifty_two_week_low": None,
            "currency": "USD",
        }
    except Exception as e:
        log.warning("download_fallback_failed ticker=%s error=%s", ticker, e)
        raise ValueError(f"yf.download fallback failed for {ticker}: {e}") from e


def get_quote(ticker: str) -> dict:
    t = _ticker(ticker)
    price = None
    prev_close = None
    info = None
    full: dict = {}

    # Primary path: fast_info (lightweight) then info (heavier quoteSummary)
    def _read_fast_info():
        fi = t.fast_info
        return fi, getattr(fi, "last_price", None), getattr(fi, "previous_close", None)

    try:
        info, price, prev_close = _retry_on_rate_limit(_read_fast_info, label=f"fast_info:{ticker}")
    except Exception as e:
        log.warning("yfinance_fast_info_failed ticker=%s error=%s", ticker, e)

    try:
        # t.info can come back None rather than raising when Yahoo refuses the
        # quoteSummary call, so normalise it before the .get calls below.
        full = _retry_on_rate_limit(lambda: t.info, label=f"info:{ticker}") or {}
        if price is None:
            price = full.get("currentPrice") or full.get("regularMarketPrice")
    except Exception as e:
        log.warning("yfinance_info_failed ticker=%s error=%s", ticker, e)

    # Fallback: history endpoint
    if price is None:
        try:
            hist = t.history(period="5d")
            if not hist.empty:
                price = round(float(hist["Close"].iloc[-1]), 4)
                if prev_close is None and len(hist) >= 2:
                    prev_close = float(hist["Close"].iloc[-2])
        except Exception:
            pass

    # Last resort: yf.download (different Yahoo endpoint, more geo-permissive)
    if price is None:
        return _download_fallback(ticker)

    change_pct = None
    if price is not None and prev_close is not None and prev_close != 0:
        change_pct = round((price - prev_close) / prev_close * 100, 2)

    # Build result from whatever info/full we managed to get
    volume = None
    market_cap = None
    pe_ratio = None
    high_52w = None
    low_52w = None
    currency = "USD"

    try:
        if info is not None:
            volume = getattr(info, "three_month_average_volume", None)
            market_cap = getattr(info, "market_cap", None) or full.get("marketCap")
            high_52w = getattr(info, "year_high", None) or full.get("fiftyTwoWeekHigh")
            low_52w = getattr(info, "year_low", None) or full.get("fiftyTwoWeekLow")
        else:
            market_cap = full.get("marketCap")
            high_52w = full.get("fiftyTwoWeekHigh")
            low_52w = full.get("fiftyTwoWeekLow")
        pe_ratio = full.get("trailingPE")
        currency = full.get("currency", "USD")
    except Exception as e:
        # Field extraction failed (often a rate limit). Leave the derived
        # fields as None but log it so the gap is diagnosable rather than
        # silently attributed to "no data".
        log.warning("yfinance_quote_fields_failed ticker=%s error=%s", ticker, e)

    return {
        "ticker": ticker.upper(),
        "current_price": price,
        "change_pct": change_pct,
        "volume": volume,
        "market_cap": market_cap,
        "pe_ratio": pe_ratio,
        "fifty_two_week_high": high_52w,
        "fifty_two_week_low": low_52w,
        "currency": currency,
    }


def get_fundamentals(ticker: str) -> dict:
    t = _ticker(ticker)
    info = _retry_on_rate_limit(lambda: t.info, label=f"fundamentals:{ticker}")
    if not info:
        raise ValueError(f"yfinance returned no fundamental data for {ticker}")

    result = {
        "ticker": ticker.upper(),
        "revenue": info.get("totalRevenue"),
        "eps": info.get("trailingEps"),
        "debt_to_equity": info.get("debtToEquity"),
        "profit_margin": info.get("profitMargins"),
        "revenue_growth_yoy": info.get("revenueGrowth"),
        "analyst_target": info.get("targetMeanPrice"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "description": (info.get("longBusinessSummary") or "")[:500],
    }

    # If all meaningful fields are None, Yahoo likely returned an empty/blocked
    # response. Raise so the caller can try Alpha Vantage fallback.
    meaningful_keys = ("revenue", "eps", "sector", "beta", "profit_margin")
    if not any(result.get(k) is not None for k in meaningful_keys):
        raise ValueError(f"yfinance returned no fundamental data for {ticker}")

    return result


def get_earnings_calendar(ticker: str) -> dict:
    """Next earnings date + EPS estimate.

    Uses `.calendar` rather than `.get_earnings_dates()` — the latter requires
    an optional `lxml` dependency this project doesn't otherwise need, and
    yfinance's earnings-calendar surfaces have historically changed shape
    across releases, so this is deliberately defensive.
    """
    t = _ticker(ticker)
    try:
        cal = t.calendar
    except Exception:
        return {}
    if not isinstance(cal, dict):
        return {}

    raw_dates = cal.get("Earnings Date")
    if not raw_dates:
        return {}
    dates = raw_dates if isinstance(raw_dates, (list, tuple)) else [raw_dates]
    if not dates:
        return {}

    try:
        next_date = min(dates)
        days_until = (next_date - _date.today()).days
    except (TypeError, ValueError):
        return {}

    return {
        "next_earnings_date": str(next_date),
        "days_until_earnings": days_until,
        "eps_estimate": cal.get("Earnings Average"),
    }


def get_price_history(ticker: str, period: str = "3mo") -> list[dict]:
    t = _ticker(ticker)
    hist = _retry_on_rate_limit(lambda: t.history(period=period), label=f"history:{ticker}")
    records = []
    for date, row in hist.iterrows():
        vol = row["Volume"]
        records.append(
            {
                "date": str(date.date()),
                "open": round(row["Open"], 4),
                "high": round(row["High"], 4),
                "low": round(row["Low"], 4),
                "close": round(row["Close"], 4),
                "volume": int(vol) if not (isinstance(vol, float) and math.isnan(vol)) else 0,
            }
        )
    return records
