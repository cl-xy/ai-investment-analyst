"""Unit tests for the auto sector-peer comparison node."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from src.agent.nodes.peer_compare import peer_compare_node


def _state(tickers, ticker_analyses):
    return {"tickers_to_analyze": tickers, "ticker_analyses": ticker_analyses}


def _primary_analysis(sector="Technology"):
    return {"ticker": "AAPL", "fundamentals": {"sector": sector}}


@pytest.mark.asyncio
async def test_skips_when_multiple_tickers_requested():
    state = _state(["AAPL", "MSFT"], {"AAPL": _primary_analysis(), "MSFT": _primary_analysis()})
    result = await peer_compare_node(state)
    assert result == {}


@pytest.mark.asyncio
async def test_skips_when_primary_analysis_missing():
    state = _state(["AAPL"], {})
    result = await peer_compare_node(state)
    assert result == {}


@pytest.mark.asyncio
async def test_skips_when_sector_unknown():
    state = _state(["AAPL"], {"AAPL": {"ticker": "AAPL", "fundamentals": {}}})
    result = await peer_compare_node(state)
    assert result == {}


@pytest.mark.asyncio
async def test_skips_when_sector_has_no_mapped_peers():
    state = _state(
        ["ZZZZ"], {"ZZZZ": {"ticker": "ZZZZ", "fundamentals": {"sector": "Not A Real Sector"}}}
    )
    result = await peer_compare_node(state)
    assert result == {}


@pytest.mark.asyncio
async def test_uses_recent_cached_analysis_when_available():
    state = _state(["AAPL"], {"AAPL": _primary_analysis()})

    cached_row = {
        "ticker": "MSFT",
        "signal": "buy",
        "confidence": "high",
        "price_data": json.dumps({"current_price": 420.0, "pe_ratio": 35.0}),
        "fundamentals": json.dumps({"revenue_growth_yoy": 0.15, "profit_margin": 0.35}),
    }

    async def _fetchrow_side_effect(query, ticker, *rest):
        return cached_row if ticker == "MSFT" else None

    with patch("src.agent.nodes.peer_compare.fetchrow", new_callable=AsyncMock) as mock_fetchrow:
        mock_fetchrow.side_effect = _fetchrow_side_effect
        result = await peer_compare_node(state)

    assert "peer_comparison" in result
    peers = result["peer_comparison"]["peers"]
    msft = next(p for p in peers if p["ticker"] == "MSFT")
    assert msft["source"] == "cached_analysis"
    assert msft["signal"] == "buy"
    assert msft["current_price"] == 420.0


@pytest.mark.asyncio
async def test_falls_back_to_fundamentals_only_when_no_cache(monkeypatch):
    state = _state(["AAPL"], {"AAPL": _primary_analysis()})

    with patch("src.agent.nodes.peer_compare.fetchrow", new_callable=AsyncMock) as mock_fetchrow:
        mock_fetchrow.return_value = None

        def _fake_get_quote(ticker):
            return {"current_price": 300.0, "pe_ratio": 28.0}

        def _fake_get_fundamentals(ticker):
            return {"revenue_growth_yoy": 0.1, "profit_margin": 0.2, "sector": "Technology"}

        monkeypatch.setattr("src.agent.nodes.peer_compare.yf_client.get_quote", _fake_get_quote)
        monkeypatch.setattr(
            "src.agent.nodes.peer_compare.yf_client.get_fundamentals", _fake_get_fundamentals
        )

        result = await peer_compare_node(state)

    assert "peer_comparison" in result
    peers = result["peer_comparison"]["peers"]
    assert len(peers) == 2  # Technology sector has enough peers to fill _MAX_PEERS
    assert all(p["source"] == "fundamentals_only" for p in peers)
    assert all(p["signal"] is None for p in peers)


@pytest.mark.asyncio
async def test_skips_peer_entirely_when_both_paths_fail(monkeypatch):
    state = _state(["AAPL"], {"AAPL": _primary_analysis()})

    with patch("src.agent.nodes.peer_compare.fetchrow", new_callable=AsyncMock) as mock_fetchrow:
        mock_fetchrow.return_value = None

        def _raise(*a, **k):
            raise RuntimeError("yfinance unavailable")

        monkeypatch.setattr("src.agent.nodes.peer_compare.yf_client.get_quote", _raise)
        monkeypatch.setattr("src.agent.nodes.peer_compare.yf_client.get_fundamentals", _raise)

        result = await peer_compare_node(state)

    # Both candidate peers failed to resolve -> no peer_comparison at all
    assert result == {}


@pytest.mark.asyncio
async def test_never_calls_alpha_vantage_module():
    """Peer enrichment must bypass market_server's Alpha Vantage fallback entirely."""
    import src.mcp_servers.market_server.sources.alpha_vantage_market as av

    state = _state(["AAPL"], {"AAPL": _primary_analysis()})

    with patch("src.agent.nodes.peer_compare.fetchrow", new_callable=AsyncMock) as mock_fetchrow:
        mock_fetchrow.return_value = None
        with (
            patch.object(av, "get_quote") as mock_av_quote,
            patch.object(av, "get_fundamentals") as mock_av_fundamentals,
        ):
            await peer_compare_node(state)

    mock_av_quote.assert_not_called()
    mock_av_fundamentals.assert_not_called()
