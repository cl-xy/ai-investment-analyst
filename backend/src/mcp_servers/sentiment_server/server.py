from dotenv import load_dotenv

load_dotenv()

from fastmcp import FastMCP

from .cache import get_cached_sentiment, set_cached_sentiment
from .sources import stocktwits

mcp = FastMCP("sentiment-server")


@mcp.tool()
def get_ticker_sentiment(ticker: str) -> dict:
    """
    Fetch recent StockTwits retail sentiment for a ticker (no auth required).
    Returns message_count, bullish_count, bearish_count, unlabeled_count,
    bullish_ratio, sample_messages. Returns {} if unavailable.
    """
    cache_key = ticker.strip().upper()
    cached = get_cached_sentiment(cache_key)
    if cached is not None:
        return cached
    data = stocktwits.get_ticker_sentiment(cache_key)
    # Cache both successful and empty results to prevent repeated API calls
    # for unavailable tickers within the TTL window
    result = data or {}
    set_cached_sentiment(cache_key, result)
    return result


if __name__ == "__main__":
    mcp.run()
