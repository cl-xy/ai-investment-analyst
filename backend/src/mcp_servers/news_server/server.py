from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP

from .cache import _headlines_cache, _news_cache
from .sources import newsapi, rss

mcp = FastMCP("news-server")


def _fetch_ticker_news(ticker: str, days_back: int, max_articles: int) -> list[dict]:
    # Fallback chain: NewsAPI → Yahoo RSS → Google RSS
    articles = newsapi.get_ticker_news(ticker, days_back, max_articles)
    if articles:
        return articles
    articles = rss.get_ticker_news_yahoo(ticker, max_articles)
    if articles:
        return articles
    return rss.get_ticker_news_google(ticker, max_articles)


@mcp.tool()
def get_ticker_news(ticker: str, days_back: int = 7, max_articles: int = 10) -> list[dict]:
    """
    Fetch recent news articles for a stock ticker.
    Returns list of {title, url, published_at, source, snippet}.
    Falls back through NewsAPI → Yahoo RSS → Google RSS.
    """
    cache_key = f"{ticker.upper()}:{days_back}:{max_articles}"
    if cache_key in _news_cache:
        return _news_cache[cache_key]
    articles = _fetch_ticker_news(ticker.upper(), days_back, max_articles)
    _news_cache[cache_key] = articles
    return articles


@mcp.tool()
def get_market_headlines(category: str = "business", limit: int = 20) -> list[dict]:
    """
    Fetch top market/business headlines.
    Returns list of {title, url, published_at, source}.
    """
    cache_key = f"headlines:{category}:{limit}"
    if cache_key in _headlines_cache:
        return _headlines_cache[cache_key]
    headlines = newsapi.get_market_headlines(category, limit)
    if not headlines:
        headlines = rss.get_market_headlines_rss(limit)
    _headlines_cache[cache_key] = headlines
    return headlines


if __name__ == "__main__":
    mcp.run()
