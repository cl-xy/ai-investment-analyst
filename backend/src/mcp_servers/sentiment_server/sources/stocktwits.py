"""
StockTwits public API client — retail sentiment for a ticker.

No API key required (public symbol stream endpoint), so this is treated the
same way SEC EDGAR is: best-effort, defensive, never raises. StockTwits
sentiment tagging is user-self-reported and can be noisy/manipulated, so it's
meant as a minor corroborating/contrarian signal, not a primary driver.
"""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)
_BASE_URL = "https://api.stocktwits.com/api/2/streams/symbol"
_HEADERS = {"User-Agent": "ai-investment-analyst/1.0 (github.com/cl-xy/ai-investment-analyst)"}

# Module-level client for connection pooling. httpx.Client is thread-safe for
# concurrent reads and the cache lock already serializes writes.
_client = httpx.Client(headers=_HEADERS, timeout=_TIMEOUT)

# Strict ticker validation: letters, digits, dots, hyphens, 1-12 chars.
# Covers standard symbols (AAPL), class shares (BRK.B), and crypto (BTC.X).
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,12}$")


def get_ticker_sentiment(ticker: str, max_messages: int = 30) -> dict:
    """
    Fetch recent StockTwits messages for a ticker and summarize sentiment.

    Returns {message_count, bullish_count, bearish_count, unlabeled_count,
    bullish_ratio, sample_messages}, or {} if unavailable (no key required,
    but the public endpoint can rate-limit or the ticker may have no stream).

    This is a blocking (synchronous) function. Callers in async contexts
    should dispatch via asyncio.to_thread or a threadpool executor.
    """
    try:
        # Validate inputs
        if not isinstance(ticker, str) or not ticker.strip():
            return {}
        symbol = ticker.strip().upper()
        if not _TICKER_RE.match(symbol):
            return {}

        max_messages = max(1, int(max_messages))

        url = f"{_BASE_URL}/{symbol}.json"

        r = _client.get(url)
        r.raise_for_status()
        data = r.json()

        if not isinstance(data, dict):
            return {}
        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            return {}
        messages = messages[:max_messages]

        bullish = 0
        bearish = 0
        unlabeled = 0
        samples: list[str] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            entities = m.get("entities")
            if not isinstance(entities, dict):
                entities = {}
            sentiment = entities.get("sentiment")
            if not isinstance(sentiment, dict):
                sentiment = {}
            basic = sentiment.get("basic")
            if basic == "Bullish":
                bullish += 1
            elif basic == "Bearish":
                bearish += 1
            else:
                unlabeled += 1
            if len(samples) < 5:
                body = m.get("body")
                if isinstance(body, str) and body.strip():
                    samples.append(body[:200])

        labeled = bullish + bearish
        bullish_ratio = round(bullish / labeled, 2) if labeled else None

        return {
            "message_count": len(messages),
            "bullish_count": bullish,
            "bearish_count": bearish,
            "unlabeled_count": unlabeled,
            "bullish_ratio": bullish_ratio,
            "sample_messages": samples,
        }
    except Exception:
        logger.debug("StockTwits fetch failed for ticker=%r", ticker, exc_info=True)
        return {}
