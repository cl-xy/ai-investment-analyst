from datetime import date as _date

import yfinance as yf


def get_quote(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.fast_info
    full = t.info
    price = getattr(info, "last_price", None)
    prev_close = getattr(info, "previous_close", None)
    change_pct = None
    if price is not None and prev_close:
        change_pct = round((price - prev_close) / prev_close * 100, 2)
    return {
        "ticker": ticker.upper(),
        "current_price": price,
        "change_pct": change_pct,
        "volume": getattr(info, "three_month_average_volume", None),
        "market_cap": getattr(info, "market_cap", None),
        "pe_ratio": full.get("trailingPE"),
        "fifty_two_week_high": getattr(info, "year_high", None) or full.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": getattr(info, "year_low", None) or full.get("fiftyTwoWeekLow"),
        "currency": full.get("currency", "USD"),
    }


def get_fundamentals(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info
    return {
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
        "description": info.get("longBusinessSummary", "")[:500],
    }


def get_earnings_calendar(ticker: str) -> dict:
    """Next earnings date + EPS estimate.

    Uses `.calendar` rather than `.get_earnings_dates()` — the latter requires
    an optional `lxml` dependency this project doesn't otherwise need, and
    yfinance's earnings-calendar surfaces have historically changed shape
    across releases, so this is deliberately defensive.
    """
    t = yf.Ticker(ticker)
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
    t = yf.Ticker(ticker)
    hist = t.history(period=period)
    records = []
    for date, row in hist.iterrows():
        records.append(
            {
                "date": str(date.date()),
                "open": round(row["Open"], 4),
                "high": round(row["High"], 4),
                "low": round(row["Low"], 4),
                "close": round(row["Close"], 4),
                "volume": int(row["Volume"]),
            }
        )
    return records
