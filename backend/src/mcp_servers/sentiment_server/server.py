from dotenv import load_dotenv

load_dotenv()

from fastmcp import FastMCP

from .cache import _sentiment_cache
from .sources import stocktwits

mcp = FastMCP("sentiment-server")


@mcp.tool()
def get_ticker_sentiment(ticker: str) -> dict:
    """
    Fetch recent StockTwits retail sentiment for a ticker (no auth required).
    Returns message_count, bullish_count, bearish_count, unlabeled_count,
    bullish_ratio, sample_messages. Returns {} if unavailable.
    """
    cache_key = ticker.upper()
    if cache_key in _sentiment_cache:
        return _sentiment_cache[cache_key]
    data = stocktwits.get_ticker_sentiment(cache_key)
    if data:
        _sentiment_cache[cache_key] = data
    return data


if __name__ == "__main__":
    mcp.run()
