"""Unit tests for the yfinance client's earnings calendar wrapper.

This is the most shape-fragile part of the market data client — yfinance's
`.calendar`/`.get_earnings_dates()` surfaces have changed across releases —
so these tests focus on defensive parsing of odd/missing shapes.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from src.mcp_servers.market_server.sources import yfinance_client as client


def _mock_ticker(calendar):
    mock = MagicMock()
    mock.calendar = calendar
    return mock


def test_get_earnings_calendar_parses_upcoming_date():
    future_date = date.today() + timedelta(days=17)
    calendar = {
        "Earnings Date": [future_date],
        "Earnings Average": 1.89,
    }
    with patch.object(client.yf, "Ticker", return_value=_mock_ticker(calendar)):
        result = client.get_earnings_calendar("AAPL")

    assert result["next_earnings_date"] == str(future_date)
    assert result["days_until_earnings"] == 17
    assert result["eps_estimate"] == 1.89


def test_get_earnings_calendar_picks_earliest_of_multiple_dates():
    d1 = date.today() + timedelta(days=30)
    d2 = date.today() + timedelta(days=17)
    calendar = {"Earnings Date": [d1, d2]}
    with patch.object(client.yf, "Ticker", return_value=_mock_ticker(calendar)):
        result = client.get_earnings_calendar("AAPL")

    assert result["next_earnings_date"] == str(d2)


def test_get_earnings_calendar_returns_empty_when_no_date():
    calendar = {"Dividend Date": date.today()}
    with patch.object(client.yf, "Ticker", return_value=_mock_ticker(calendar)):
        result = client.get_earnings_calendar("AAPL")

    assert result == {}


def test_get_earnings_calendar_returns_empty_on_non_dict_calendar():
    """Older/newer yfinance versions have returned a DataFrame here."""
    with patch.object(client.yf, "Ticker", return_value=_mock_ticker(MagicMock())):
        result = client.get_earnings_calendar("AAPL")

    assert result == {}


def test_get_earnings_calendar_returns_empty_when_calendar_raises():
    mock = MagicMock()
    type(mock).calendar = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    with patch.object(client.yf, "Ticker", return_value=mock):
        result = client.get_earnings_calendar("AAPL")

    assert result == {}


def test_get_earnings_calendar_handles_single_date_not_in_list():
    """Defensive: some yfinance versions return a bare date, not a list."""
    single_date = date.today() + timedelta(days=5)
    calendar = {"Earnings Date": single_date}
    with patch.object(client.yf, "Ticker", return_value=_mock_ticker(calendar)):
        result = client.get_earnings_calendar("AAPL")

    assert result["next_earnings_date"] == str(single_date)
    assert result["days_until_earnings"] == 5


# --- rate limit retry ---


def test_retry_on_rate_limit_recovers_after_429():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise client.YFRateLimitError()
        return "ok"

    with patch.object(client.time, "sleep") as sleep:
        assert client._retry_on_rate_limit(flaky, label="t") == "ok"

    assert calls["n"] == 3
    assert sleep.call_count == 2


def test_retry_on_rate_limit_gives_up_after_max_retries():
    def always_limited():
        raise Exception("Too Many Requests. Rate limited. Try after a while.")

    with patch.object(client.time, "sleep"):
        try:
            client._retry_on_rate_limit(always_limited, label="t")
        except Exception as e:
            assert "Too Many Requests" in str(e)
        else:
            raise AssertionError("expected the rate limit error to propagate")


def test_retry_on_rate_limit_does_not_retry_other_errors():
    calls = {"n": 0}

    def broken():
        calls["n"] += 1
        raise ValueError("bad ticker")

    with patch.object(client.time, "sleep") as sleep:
        try:
            client._retry_on_rate_limit(broken, label="t")
        except ValueError:
            pass

    assert calls["n"] == 1
    sleep.assert_not_called()


def test_get_quote_fills_pe_and_market_cap_after_info_rate_limit():
    calls = {"n": 0}

    class FakeTicker:
        fast_info = MagicMock(last_price=100.0, previous_close=98.0, year_high=120.0, year_low=80.0)
        fast_info.market_cap = None

        @property
        def info(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise client.YFRateLimitError()
            return {"trailingPE": 31.5, "marketCap": 3_000_000_000_000, "currency": "USD"}

    with (
        patch.object(client.yf, "Ticker", return_value=FakeTicker()),
        patch.object(client.time, "sleep"),
    ):
        result = client.get_quote("NVDA")

    assert result["pe_ratio"] == 31.5
    assert result["market_cap"] == 3_000_000_000_000


def test_ticker_uses_yfinance_default_session():
    """A custom requests.Session bypasses yfinance's curl_cffi session, which is
    what Yahoo was rejecting with 429 from the production IP."""
    with patch.object(client.yf, "Ticker") as ticker_cls:
        client._ticker("NVDA")

    ticker_cls.assert_called_once_with("NVDA")


def test_get_quote_survives_info_returning_none():
    class FakeTicker:
        fast_info = MagicMock(last_price=100.0, previous_close=98.0, year_high=120.0, year_low=80.0)
        fast_info.market_cap = None
        info = None

    with patch.object(client.yf, "Ticker", return_value=FakeTicker()):
        result = client.get_quote("NVDA")

    assert result["current_price"] == 100.0
    assert result["pe_ratio"] is None


def test_get_fundamentals_raises_when_info_is_none():
    class FakeTicker:
        info = None

    with patch.object(client.yf, "Ticker", return_value=FakeTicker()):
        try:
            client.get_fundamentals("NVDA")
        except ValueError as e:
            assert "no fundamental data" in str(e)
        else:
            raise AssertionError("expected ValueError")
