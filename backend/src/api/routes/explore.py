"""
Explore route — returns trending US stocks from Yahoo Finance.
Results are cached in-memory for 5 minutes to reduce external API calls.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import yfinance as yf
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException

from ..schemas import ExploreResponse, NewsItem, PricePoint, StockDetail, TrendingStock

router = APIRouter()

_TRENDING_URL = "https://query1.finance.yahoo.com/v1/finance/trending/US"
_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; investment-analyst/1.0)"
}
_CACHE: TTLCache = TTLCache(maxsize=1, ttl=300)       # 5-minute TTL for trending list
_DETAIL_CACHE: TTLCache = TTLCache(maxsize=50, ttl=900)  # 15-minute TTL per ticker
_CACHE_KEY = "explore"
_YF_EXECUTOR = ThreadPoolExecutor(max_workers=4)


async def _fetch_trending_symbols(client: httpx.AsyncClient, count: int = 20) -> list[str]:
    resp = await client.get(
        _TRENDING_URL,
        params={"count": count, "region": "US"},
        headers=_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
    return [q["symbol"] for q in quotes if q.get("symbol")]


async def _fetch_chart(client: httpx.AsyncClient, symbol: str) -> dict:
    """Fetch price/change/volume/name for a single symbol via the v8 chart endpoint."""
    try:
        resp = await client.get(
            _CHART_URL.format(symbol=symbol),
            params={"interval": "1d", "range": "1d"},
            headers=_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        meta = resp.json().get("chart", {}).get("result", [{}])[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("chartPreviousClose")
        change_pct = (
            (price - prev_close) / prev_close * 100
            if price is not None and prev_close
            else None
        )
        return {
            "symbol": symbol,
            "shortName": meta.get("shortName") or meta.get("longName"),
            "regularMarketPrice": price,
            "regularMarketChangePercent": change_pct,
            "regularMarketVolume": meta.get("regularMarketVolume"),
        }
    except Exception:
        return {"symbol": symbol}


async def _fetch_quotes(client: httpx.AsyncClient, symbols: list[str]) -> dict[str, dict]:
    """Fetch price/change/volume/name for a list of symbols concurrently."""
    results = await asyncio.gather(*[_fetch_chart(client, s) for s in symbols])
    return {item["symbol"]: item for item in results}


async def _fetch_price_history(client: httpx.AsyncClient, symbol: str) -> list[PricePoint]:
    """Fetch 30-day daily close prices for a symbol."""
    try:
        resp = await client.get(
            _CHART_URL.format(symbol=symbol),
            params={"interval": "1d", "range": "1mo"},
            headers=_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json().get("chart", {}).get("result", [{}])[0]
        timestamps = result.get("timestamp", [])
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        points: list[PricePoint] = []
        for ts, close in zip(timestamps, closes):
            if close is not None:
                date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                points.append(PricePoint(date=date, close=round(close, 2)))
        return points
    except Exception:
        return []


async def _fetch_yf_info(ticker: str) -> dict:
    """Fetch company info via yfinance (runs in thread pool)."""
    loop = asyncio.get_event_loop()

    def _get() -> dict:
        try:
            return yf.Ticker(ticker).info or {}
        except Exception:
            return {}

    return await loop.run_in_executor(_YF_EXECUTOR, _get)


async def _fetch_yf_news(ticker: str) -> list[NewsItem]:
    """Fetch recent news headlines + URLs via yfinance (runs in thread pool)."""
    loop = asyncio.get_event_loop()

    def _get() -> list[NewsItem]:
        try:
            items: list[NewsItem] = []
            for n in (yf.Ticker(ticker).news or [])[:4]:
                # yfinance ≥0.2.x wraps content in a "content" dict
                content = n.get("content", {})
                title = content.get("title") or n.get("title", "")
                url = (
                    content.get("canonicalUrl", {}).get("url")
                    or content.get("clickThroughUrl", {}).get("url")
                    or n.get("link")
                    or n.get("url")
                )
                if title:
                    items.append(NewsItem(title=title, url=url or None))
            return items
        except Exception:
            return []

    return await loop.run_in_executor(_YF_EXECUTOR, _get)


@router.get("/explore", response_model=ExploreResponse)
async def get_explore() -> ExploreResponse:
    cached = _CACHE.get(_CACHE_KEY)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient() as client:
            symbols = await _fetch_trending_symbols(client)
            if not symbols:
                raise HTTPException(status_code=502, detail="No trending symbols returned")
            quotes = await _fetch_quotes(client, symbols)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Yahoo Finance error: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Yahoo Finance: {exc}") from exc

    stocks: list[TrendingStock] = []
    for rank, symbol in enumerate(symbols, start=1):
        q = quotes.get(symbol, {})
        stocks.append(
            TrendingStock(
                rank=rank,
                ticker=symbol,
                name=q.get("shortName") or symbol,
                price=q.get("regularMarketPrice"),
                change_pct=q.get("regularMarketChangePercent"),
                volume=q.get("regularMarketVolume"),
            )
        )

    response = ExploreResponse(stocks=stocks, updated_at=datetime.now(timezone.utc))
    _CACHE[_CACHE_KEY] = response
    return response


@router.get("/explore/{ticker}/detail", response_model=StockDetail)
async def get_stock_detail(ticker: str) -> StockDetail:
    ticker = ticker.upper()
    cached = _DETAIL_CACHE.get(ticker)
    if cached is not None:
        return cached

    async with httpx.AsyncClient() as client:
        price_history, info, news_headlines = await asyncio.gather(
            _fetch_price_history(client, ticker),
            _fetch_yf_info(ticker),
            _fetch_yf_news(ticker),
        )

    detail = StockDetail(
        ticker=ticker,
        industry=info.get("industry") or info.get("sector") or None,
        description=info.get("longBusinessSummary") or None,
        price_history=price_history,
        trending_reason=news_headlines,
    )
    _DETAIL_CACHE[ticker] = detail
    return detail
