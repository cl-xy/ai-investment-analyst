"""Regression tests for Explore's durable last-known-good company profile."""

from unittest.mock import AsyncMock, patch

import pytest

from src.api.routes import explore


@pytest.fixture(autouse=True)
def reset_explore_caches():
    explore._DETAIL_CACHE.clear()
    explore._DETAIL_LOCKS.clear()
    yield
    explore._DETAIL_CACHE.clear()
    explore._DETAIL_LOCKS.clear()


async def _price_history(*_args, **_kwargs):
    return [explore.PricePoint(date="2026-09-30", close=100.0)]


async def _news(*_args, **_kwargs):
    return []


async def _get_detail(ticker: str):
    """Call the endpoint logic without involving SlowAPI's HTTP wrapper."""
    return await explore.get_stock_detail.__wrapped__(None, ticker)


@pytest.mark.asyncio
async def test_saves_successful_company_description_for_later_fallback():
    saved = AsyncMock()
    with (
        patch.object(explore, "_fetch_price_history", _price_history),
        patch.object(
            explore,
            "_fetch_yf_info",
            AsyncMock(return_value={"longBusinessSummary": "CBRS description", "industry": "Tech"}),
        ),
        patch.object(explore, "_fetch_yf_news", _news),
        patch.object(explore.cache_manager, "store", saved),
    ):
        detail = await _get_detail("CBRS")

    assert detail.description == "CBRS description"
    assert detail.industry == "Tech"
    saved.assert_awaited_once_with(
        "yfinance", "get_company_profile", "CBRS", {"description": "CBRS description"}
    )


@pytest.mark.asyncio
async def test_uses_last_known_description_when_yahoo_profile_is_empty():
    cached_profile = AsyncMock(return_value=({"description": "Saved CBRS description"}, "src", True))
    with (
        patch.object(explore, "_fetch_price_history", _price_history),
        patch.object(explore, "_fetch_yf_info", AsyncMock(return_value={})),
        patch.object(explore, "_fetch_yf_news", _news),
        patch.object(explore.cache_manager, "get_cached_only", cached_profile),
        patch.object(explore.cache_manager, "store", AsyncMock()),
    ):
        detail = await _get_detail("CBRS")

    assert detail.description == "Saved CBRS description"
    cached_profile.assert_awaited_once_with("yfinance", "get_company_profile", "CBRS")
    assert explore._DETAIL_CACHE["CBRS"].description == "Saved CBRS description"


@pytest.mark.asyncio
async def test_does_not_cache_a_blank_profile_response():
    cached_profile = AsyncMock(return_value=(None, "", False))
    with (
        patch.object(explore, "_fetch_price_history", _price_history),
        patch.object(explore, "_fetch_yf_info", AsyncMock(return_value={})),
        patch.object(explore, "_fetch_yf_news", _news),
        patch.object(explore.cache_manager, "get_cached_only", cached_profile),
    ):
        detail = await _get_detail("CBRS")

    assert detail.description is None
    assert "CBRS" not in explore._DETAIL_CACHE


@pytest.mark.asyncio
async def test_discards_legacy_blank_detail_cache_and_recovers_from_profile_cache():
    explore._DETAIL_CACHE["CBRS"] = explore.StockDetail(
        ticker="CBRS", industry=None, description=None, price_history=[], trending_reason=[]
    )
    cached_profile = AsyncMock(return_value=({"description": "Recovered description"}, "src", True))
    with (
        patch.object(explore, "_fetch_price_history", _price_history),
        patch.object(explore, "_fetch_yf_info", AsyncMock(return_value={})),
        patch.object(explore, "_fetch_yf_news", _news),
        patch.object(explore.cache_manager, "get_cached_only", cached_profile),
    ):
        detail = await _get_detail("CBRS")

    assert detail.description == "Recovered description"
    assert explore._DETAIL_CACHE["CBRS"].description == "Recovered description"
