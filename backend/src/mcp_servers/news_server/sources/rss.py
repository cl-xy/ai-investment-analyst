import feedparser


def _parse_feed(url: str, max_articles: int) -> list[dict]:
    feed = feedparser.parse(url)
    results = []
    for entry in feed.entries[:max_articles]:
        results.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published_at": entry.get("published", ""),
            "source": feed.feed.get("title", "RSS"),
            "snippet": (entry.get("summary") or "")[:400],
        })
    return results


def get_ticker_news_yahoo(ticker: str, max_articles: int = 10) -> list[dict]:
    url = f"https://finance.yahoo.com/rss/headline?s={ticker}"
    return _parse_feed(url, max_articles)


def get_ticker_news_google(ticker: str, max_articles: int = 10) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
    return _parse_feed(url, max_articles)


def get_market_headlines_rss(max_articles: int = 20) -> list[dict]:
    url = "https://finance.yahoo.com/news/rssindex"
    return _parse_feed(url, max_articles)
