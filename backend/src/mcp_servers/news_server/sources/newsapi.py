import os
from datetime import datetime, timedelta, timezone

import requests
from newsapi import NewsApiClient

_TIMEOUT = 30  # seconds


class _TimeoutSession(requests.Session):
    """Session subclass that enforces a default timeout on all requests."""

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", _TIMEOUT)
        return super().request(*args, **kwargs)


def _client() -> NewsApiClient | None:
    key = os.environ.get("NEWS_API_KEY")
    if not key:
        return None
    session = _TimeoutSession()
    return NewsApiClient(api_key=key, session=session)


def get_ticker_news(ticker: str, days_back: int = 7, max_articles: int = 10) -> list[dict] | None:
    client = _client()
    if client is None:
        return None
    from_date = (datetime.now(tz=timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        response = client.get_everything(
            q=ticker,
            from_param=from_date,
            language="en",
            sort_by="publishedAt",
            page_size=max_articles,
        )
    except Exception:
        return None
    articles = response.get("articles", [])
    return [
        {
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "published_at": a.get("publishedAt", ""),
            "source": a.get("source", {}).get("name", ""),
            "snippet": (a.get("description") or a.get("content") or "")[:400],
        }
        for a in articles
    ]


def get_market_headlines(category: str = "business", limit: int = 20) -> list[dict] | None:
    client = _client()
    if client is None:
        return None
    try:
        response = client.get_top_headlines(category=category, language="en", page_size=limit)
    except Exception:
        return None
    articles = response.get("articles", [])
    return [
        {
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "published_at": a.get("publishedAt", ""),
            "source": a.get("source", {}).get("name", ""),
        }
        for a in articles
    ]
