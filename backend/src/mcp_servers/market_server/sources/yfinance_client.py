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
