import logging
import os

import httpx

from src.numeric import safe_float_or_none as _safe_float
from src.validation import validate_ticker_or_none as _validate_ticker

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"


def _key() -> str | None:
    return os.environ.get("ALPHA_VANTAGE_API_KEY")


def _safe_int(v: object) -> int | None:
    """Safely parse a value to int, returning None on failure."""
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _safe_pct(v: object) -> float | None:
    """Parse a percentage string like '1.23%' to float, returning None on failure."""
    if v is None:
        return None
    try:
        return float(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def _check_error_response(data: dict) -> str | None:
    """Check for Alpha Vantage application-level errors (rate limit, invalid key, etc).
    Returns error message if present, None otherwise."""
    for key in ("Note", "Information", "Error Message"):
        if key in data:
            return str(data[key])
    return None


def get_quote(ticker: str) -> dict | None:
    normalized = _validate_ticker(ticker)
    if not normalized:
        logger.warning("alpha_vantage: invalid ticker rejected: %r", ticker[:20])
        return None

    key = _key()
    if not key:
        return None

    try:
        r = httpx.get(
            BASE_URL,
            params={"function": "GLOBAL_QUOTE", "symbol": normalized, "apikey": key},
            timeout=10,
        )
        r.raise_for_status()
        payload = r.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        logger.warning("alpha_vantage quote failed for %s: %s", normalized, exc)
        return None

    if not isinstance(payload, dict):
        return None

    error_msg = _check_error_response(payload)
    if error_msg:
        logger.warning("alpha_vantage API error for %s: %s", normalized, error_msg[:200])
        return None

    data = payload.get("Global Quote", {})
    if not isinstance(data, dict) or not data:
        return None

    return {
        "ticker": normalized,
        "current_price": _safe_float(data.get("05. price")),
        "change_pct": _safe_pct(data.get("10. change percent")),
        "volume": _safe_int(data.get("06. volume")),
        "market_cap": None,
        "pe_ratio": None,
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
        "currency": "USD",
    }


def get_fundamentals(ticker: str) -> dict | None:
    normalized = _validate_ticker(ticker)
    if not normalized:
        logger.warning("alpha_vantage: invalid ticker rejected: %r", ticker[:20])
        return None

    key = _key()
    if not key:
        return None

    try:
        r = httpx.get(
            BASE_URL,
            params={"function": "OVERVIEW", "symbol": normalized, "apikey": key},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        logger.warning("alpha_vantage fundamentals failed for %s: %s", normalized, exc)
        return None

    if not isinstance(data, dict):
        return None

    error_msg = _check_error_response(data)
    if error_msg:
        logger.warning("alpha_vantage API error for %s: %s", normalized, error_msg[:200])
        return None

    if "Symbol" not in data:
        return None

    return {
        "ticker": normalized,
        "revenue": _safe_float(data.get("RevenueTTM")),
        "eps": _safe_float(data.get("EPS")),
        "debt_to_equity": _safe_float(data.get("DebtEquityRatio")),
        "profit_margin": _safe_float(data.get("ProfitMargin")),
        "revenue_growth_yoy": _safe_float(data.get("QuarterlyRevenueGrowthYOY")),
        "analyst_target": _safe_float(data.get("AnalystTargetPrice")),
        "dividend_yield": _safe_float(data.get("DividendYield")),
        "beta": _safe_float(data.get("Beta")),
        "sector": data.get("Sector"),
        "industry": data.get("Industry"),
        "description": str(data.get("Description") or "")[:500],
    }
