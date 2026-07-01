import os

import httpx

BASE_URL = "https://www.alphavantage.co/query"


def _key() -> str | None:
    return os.environ.get("ALPHA_VANTAGE_API_KEY")


def get_quote(ticker: str) -> dict | None:
    key = _key()
    if not key:
        return None
    r = httpx.get(BASE_URL, params={"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": key}, timeout=10)
    r.raise_for_status()
    data = r.json().get("Global Quote", {})
    if not data:
        return None
    return {
        "ticker": ticker.upper(),
        "current_price": float(data.get("05. price", 0)),
        "change_pct": float(data.get("10. change percent", "0%").strip("%")),
        "volume": int(data.get("06. volume", 0)),
        "market_cap": None,
        "pe_ratio": None,
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
        "currency": "USD",
    }


def get_fundamentals(ticker: str) -> dict | None:
    key = _key()
    if not key:
        return None
    r = httpx.get(BASE_URL, params={"function": "OVERVIEW", "symbol": ticker, "apikey": key}, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data or "Symbol" not in data:
        return None
    def _float(v: str) -> float | None:
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return {
        "ticker": ticker.upper(),
        "revenue": _float(data.get("RevenueTTM")),
        "eps": _float(data.get("EPS")),
        "debt_to_equity": _float(data.get("DebtToEquityRatio")),
        "profit_margin": _float(data.get("ProfitMargin")),
        "revenue_growth_yoy": None,
        "analyst_target": _float(data.get("AnalystTargetPrice")),
        "dividend_yield": _float(data.get("DividendYield")),
        "beta": _float(data.get("Beta")),
        "sector": data.get("Sector"),
        "industry": data.get("Industry"),
        "description": data.get("Description", "")[:500],
    }
