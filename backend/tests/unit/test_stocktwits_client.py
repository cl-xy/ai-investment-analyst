"""Unit tests for the StockTwits sentiment client.

No API key is required for the public symbol-stream endpoint, so these tests
focus on defensive handling of failure modes (rate limits, empty streams,
malformed responses) since there's no auth failure mode to test instead.
"""

from unittest.mock import MagicMock, patch

import httpx
from src.mcp_servers.sentiment_server.sources import stocktwits


def _mock_response(json_data=None, status_code=200, raise_for_status_exc=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if raise_for_status_exc:
        resp.raise_for_status.side_effect = raise_for_status_exc
    else:
        resp.raise_for_status.return_value = None
    return resp


def _message(sentiment=None, body="Looking strong"):
    entities = {"sentiment": {"basic": sentiment}} if sentiment else {}
    return {"body": body, "entities": entities}


def test_bullish_heavy_stream():
    messages = [_message("Bullish") for _ in range(8)] + [_message("Bearish") for _ in range(2)]
    with patch.object(
        stocktwits._client, "get", return_value=_mock_response({"messages": messages})
    ):
        result = stocktwits.get_ticker_sentiment("NVDA")

    assert result["message_count"] == 10
    assert result["bullish_count"] == 8
    assert result["bearish_count"] == 2
    assert result["bullish_ratio"] == 0.8
    assert len(result["sample_messages"]) <= 5


def test_bearish_heavy_stream():
    messages = [_message("Bearish") for _ in range(7)] + [_message("Bullish") for _ in range(1)]
    with patch.object(
        stocktwits._client, "get", return_value=_mock_response({"messages": messages})
    ):
        result = stocktwits.get_ticker_sentiment("GME")

    assert result["bearish_count"] == 7
    assert result["bullish_count"] == 1
    assert result["bullish_ratio"] == 0.12  # round(1/8, 2)


def test_empty_stream_returns_empty_dict():
    with patch.object(stocktwits._client, "get", return_value=_mock_response({"messages": []})):
        result = stocktwits.get_ticker_sentiment("ZZZZ")

    assert result == {}


def test_no_messages_key_returns_empty_dict():
    with patch.object(stocktwits._client, "get", return_value=_mock_response({})):
        result = stocktwits.get_ticker_sentiment("ZZZZ")

    assert result == {}


def test_rate_limited_403_returns_empty_dict():
    resp = _mock_response(
        raise_for_status_exc=httpx.HTTPStatusError(
            "403 Forbidden", request=MagicMock(), response=MagicMock(status_code=403)
        )
    )
    with patch.object(stocktwits._client, "get", return_value=resp):
        result = stocktwits.get_ticker_sentiment("NVDA")

    assert result == {}


def test_network_error_returns_empty_dict():
    with patch.object(stocktwits._client, "get", side_effect=httpx.ConnectError("boom")):
        result = stocktwits.get_ticker_sentiment("NVDA")

    assert result == {}


def test_unlabeled_messages_counted_separately():
    messages = [_message(None) for _ in range(3)] + [_message("Bullish")]
    with patch.object(
        stocktwits._client, "get", return_value=_mock_response({"messages": messages})
    ):
        result = stocktwits.get_ticker_sentiment("AAPL")

    assert result["unlabeled_count"] == 3
    assert result["bullish_count"] == 1


def test_all_unlabeled_gives_none_bullish_ratio():
    messages = [_message(None) for _ in range(5)]
    with patch.object(
        stocktwits._client, "get", return_value=_mock_response({"messages": messages})
    ):
        result = stocktwits.get_ticker_sentiment("AAPL")

    assert result["bullish_ratio"] is None
