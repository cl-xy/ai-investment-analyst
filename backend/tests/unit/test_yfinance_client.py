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
