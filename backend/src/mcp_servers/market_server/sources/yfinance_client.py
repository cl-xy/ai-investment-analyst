import logging
import math
import threading
from datetime import date as _date

import requests
import yfinance as yf

log = logging.getLogger(__name__)

# Thread-local storage for requests sessions. requests.Session is not
# thread-safe, and this module is called from FastAPI's thread pool.
_LOCAL = threading.local()


def _get_session() -> requests.Session:
    """Return a per-thread requests.Session with a default timeout."""
    if not hasattr(_LOCAL, "session"):
        s = requests.Session()
        s.request = lambda *args, **kwargs: requests.Session.request(  # type: ignore[method-assign, misc]
            s, *args, timeout=kwargs.pop("timeout", 20), **kwargs
        )
        _LOCAL.session = s
    return _LOCAL.session


def _ticker(symbol: str) -> yf.Ticker:
    """Create a Ticker with a timeout-enforcing session."""
    return yf.Ticker(symbol, session=_get_session())


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
    try:
        info = t.fast_info
        price = getattr(info, "last_price", None)
        prev_close = getattr(info, "previous_close", None)
    except Exception as e:
        log.warning("yfinance_fast_info_failed ticker=%s error=%s", ticker, e)

    try:
        full = t.info
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
    except Exception:
        pass

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
    info = t.info

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
    hist = t.history(period=period)
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
