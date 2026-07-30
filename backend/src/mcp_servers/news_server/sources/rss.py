import logging

import feedparser
import httpx

from src.validation import validate_ticker_or_none

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
_USER_AGENT = "Mozilla/5.0 (compatible; InvestBot/1.0)"
_MAX_ARTICLES_CEIL = 50


def _validate_ticker(ticker: str) -> str:
    """Validate ticker, returning empty string on failure."""
    return validate_ticker_or_none(ticker) or ""


def _clamp_max_articles(max_articles: int) -> int:
    """Clamp max_articles to a safe range."""
    if max_articles < 1:
        return 1
    if max_articles > _MAX_ARTICLES_CEIL:
        return _MAX_ARTICLES_CEIL
    return max_articles


def _strip_html(text: str) -> str:
    """Strip HTML tags from text (simple regex approach for RSS snippets)."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)


def _parse_feed(url: str, params: dict | None, max_articles: int) -> list[dict]:
    """Fetch and parse an RSS feed, returning structured article dicts."""
    max_articles = _clamp_max_articles(max_articles)
    try:
        r = httpx.get(
            url,
            params=params,
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )
        r.raise_for_status()
        content = r.text
    except httpx.TimeoutException:
        logger.warning("RSS feed timeout", extra={"url": url})
        return []
    except httpx.HTTPStatusError as e:
        logger.warning(
            "RSS feed HTTP error",
            extra={"url": url, "status_code": e.response.status_code},
        )
        return []
    except httpx.RequestError as e:
        logger.warning("RSS feed request error", extra={"url": url, "error": str(e)})
        return []

    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        logger.warning("RSS feed parse error (bozo)", extra={"url": url})
        return []

    results = []
    for entry in feed.entries[:max_articles]:
        results.append(
            {
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "published_at": entry.get("published", ""),
                "source": feed.feed.get("title", "RSS"),
                "snippet": _strip_html(entry.get("summary") or "")[:400],
            }
        )
    return results


def get_ticker_news_yahoo(ticker: str, max_articles: int = 10) -> list[dict]:
    ticker = _validate_ticker(ticker)
    if not ticker:
        return []
    url = "https://finance.yahoo.com/rss/headline"
    return _parse_feed(url, {"s": ticker}, max_articles)


def get_ticker_news_google(ticker: str, max_articles: int = 10) -> list[dict]:
    ticker = _validate_ticker(ticker)
    if not ticker:
        return []
    url = "https://news.google.com/rss/search"
    params = {"q": f"{ticker} stock", "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return _parse_feed(url, params, max_articles)


def get_market_headlines_rss(max_articles: int = 20) -> list[dict]:
    url = "https://finance.yahoo.com/news/rssindex"
    return _parse_feed(url, None, max_articles)
