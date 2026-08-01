from dotenv import load_dotenv

load_dotenv()

import logging

from fastmcp import FastMCP

from src.validation import validate_ticker

from .cache import _headlines_cache, _headlines_lock, _news_cache, _news_lock
from .sources import newsapi, rss

log = logging.getLogger(__name__)

mcp = FastMCP("news-server")

_VALID_CATEGORIES = {
    "business",
    "technology",
    "science",
    "health",
    "general",
    "entertainment",
    "sports",
}


def _validate_ticker(ticker: str) -> str:
    """Normalize and validate ticker. Returns uppercased ticker or raises ValueError."""
    return validate_ticker(ticker)


def _copy_articles(articles: list[dict]) -> list[dict]:
    """Return a shallow copy of the list with copied dicts to prevent cache mutation."""
    return [dict(a) for a in articles if isinstance(a, dict)]


def _fetch_ticker_news(ticker: str, days_back: int, max_articles: int) -> list[dict]:
    # Fallback chain: NewsAPI -> Yahoo RSS -> Google RSS
    # Each source is exception-isolated so failures don't skip fallbacks.
    try:
        articles = newsapi.get_ticker_news(ticker, days_back, max_articles)
        if articles:
            return articles
    except Exception as exc:
        log.warning("news-server: NewsAPI failed for %s: %s", ticker, exc)

    try:
        articles = rss.get_ticker_news_yahoo(ticker, max_articles)
        if articles:
            return articles
    except Exception as exc:
        log.warning("news-server: Yahoo RSS failed for %s: %s", ticker, exc)

    try:
        articles = rss.get_ticker_news_google(ticker, max_articles)
        if articles:
            return articles
    except Exception as exc:
        log.warning("news-server: Google RSS failed for %s: %s", ticker, exc)

    return []


@mcp.tool()
def get_ticker_news(ticker: str, days_back: int = 7, max_articles: int = 10) -> list[dict]:
    """
    Fetch recent news articles for a stock ticker.
    Returns list of {title, url, published_at, source, snippet}.
    Falls back through NewsAPI -> Yahoo RSS -> Google RSS.
    """
    try:
        ticker = _validate_ticker(ticker)
    except ValueError:
        log.warning("news-server: rejected invalid ticker %r", ticker)
        return []

    # Clamp numeric params to sane bounds
    days_back = max(1, min(days_back, 30))
    max_articles = max(1, min(max_articles, 50))

    cache_key = f"{ticker}:{days_back}:{max_articles}"
    with _news_lock:
        cached = _news_cache.get(cache_key)
    if cached is not None:
        return _copy_articles(cached)

    try:
        articles = _fetch_ticker_news(ticker, days_back, max_articles)
    except Exception as exc:
        log.warning("news-server: unexpected error fetching news for %s: %s", ticker, exc)
        articles = []

    if articles:
        with _news_lock:
            _news_cache[cache_key] = articles
    return _copy_articles(articles)


@mcp.tool()
def get_market_headlines(category: str = "business", limit: int = 20) -> list[dict]:
    """
    Fetch top market/business headlines.
    Returns list of {title, url, published_at, source}.
    """
    category = category.strip().lower()
    if category not in _VALID_CATEGORIES:
        category = "business"

    limit = max(1, min(limit, 50))

    cache_key = f"headlines:{category}:{limit}"
    with _headlines_lock:
        cached = _headlines_cache.get(cache_key)
    if cached is not None:
        return _copy_articles(cached)

    headlines: list[dict] = []
    try:
        headlines = newsapi.get_market_headlines(category, limit) or []
    except Exception as exc:
        log.warning("news-server: NewsAPI headlines failed: %s", exc)

    if not headlines:
        try:
            headlines = rss.get_market_headlines_rss(limit) or []
        except Exception as exc:
            log.warning("news-server: RSS headlines fallback failed: %s", exc)

    if headlines:
        with _headlines_lock:
            _headlines_cache[cache_key] = headlines
    return _copy_articles(headlines)


if __name__ == "__main__":
    mcp.run()
