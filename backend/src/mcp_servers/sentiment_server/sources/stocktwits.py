"""
StockTwits public API client — retail sentiment for a ticker.

No API key required (public symbol stream endpoint), so this is treated the
same way SEC EDGAR is: best-effort, defensive, never raises. StockTwits
sentiment tagging is user-self-reported and can be noisy/manipulated, so it's
meant as a minor corroborating/contrarian signal, not a primary driver.
"""

import httpx

_TIMEOUT = 15  # seconds
_BASE_URL = "https://api.stocktwits.com/api/2/streams/symbol"
_HEADERS = {"User-Agent": "ai-investment-analyst/1.0 (github.com/cl-xy/ai-investment-analyst)"}

# Module-level client reuses TCP connections across calls
_client = httpx.Client(headers=_HEADERS, timeout=_TIMEOUT)


def get_ticker_sentiment(ticker: str, max_messages: int = 30) -> dict:
    """
    Fetch recent StockTwits messages for a ticker and summarize sentiment.

    Returns {message_count, bullish_count, bearish_count, unlabeled_count,
    bullish_ratio, sample_messages}, or {} if unavailable (no key required,
    but the public endpoint can rate-limit or the ticker may have no stream).
    """
    url = f"{_BASE_URL}/{ticker.upper()}.json"
    try:
        r = _client.get(url)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return {}

    messages = data.get("messages") if isinstance(data, dict) else None
    if not messages:
        return {}
    messages = messages[:max_messages]

    bullish = 0
    bearish = 0
    unlabeled = 0
    samples: list[str] = []
    for m in messages:
        entities = m.get("entities") or {}
        sentiment = entities.get("sentiment") or {}
        basic = sentiment.get("basic")
        if basic == "Bullish":
            bullish += 1
        elif basic == "Bearish":
            bearish += 1
        else:
            unlabeled += 1
        if len(samples) < 5:
            body = m.get("body", "")
            if body:
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
