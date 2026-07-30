import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from newsapi import NewsApiClient

from src.validation import TICKER_RE

logger = logging.getLogger(__name__)

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


def _parse_article(a: dict, include_snippet: bool = False) -> dict | None:
    """Safely extract article fields, returning None for malformed entries."""
    if not isinstance(a, dict):
        return None
    source = (a.get("source") or {})
    if not isinstance(source, dict):
        source = {}
    result = {
        "title": a.get("title") or "",
        "url": a.get("url") or "",
        "published_at": a.get("publishedAt") or "",
        "source": source.get("name") or "",
    }
    if include_snippet:
        snippet = a.get("description") or a.get("content") or ""
        if not isinstance(snippet, str):
            snippet = ""
        result["snippet"] = snippet[:400]
    return result


def get_ticker_news(ticker: str, days_back: int = 7, max_articles: int = 10) -> list[dict] | None:
    if not isinstance(ticker, str) or not TICKER_RE.fullmatch(ticker.strip()):
        logger.warning("Invalid ticker rejected: %r", ticker)
        return None
    ticker = ticker.strip()

    client = _client()
    if client is None:
        return None

    try:
        from_date = (datetime.now(tz=timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        response = client.get_everything(
            q=ticker,
            from_param=from_date,
            language="en",
            sort_by="publishedAt",
            page_size=min(max(max_articles, 1), 100),
        )
        if not isinstance(response, dict):
            logger.warning("NewsAPI returned non-dict response for ticker %s", ticker)
            return None
        articles = response.get("articles") or []
        if not isinstance(articles, list):
            return None
        return [p for p in (_parse_article(a, include_snippet=True) for a in articles) if p]
    except Exception as exc:
        logger.warning("NewsAPI get_everything failed for %s: %s", ticker, exc)
        return None


def get_market_headlines(category: str = "business", limit: int = 20) -> list[dict] | None:
    client = _client()
    if client is None:
        return None

    try:
        response = client.get_top_headlines(
            category=category, language="en", page_size=min(max(limit, 1), 100)
        )
        if not isinstance(response, dict):
            logger.warning("NewsAPI returned non-dict response for headlines")
            return None
        articles = response.get("articles") or []
        if not isinstance(articles, list):
            return None
        return [p for p in (_parse_article(a, include_snippet=False) for a in articles) if p]
    except Exception as exc:
        logger.warning("NewsAPI get_top_headlines failed: %s", exc)
        return None
