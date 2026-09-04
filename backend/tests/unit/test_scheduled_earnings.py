"""Unit tests for the event-driven earnings refresh endpoint and its due-check logic."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from src.api.routes.scheduled import _ticker_due_for_earnings_refresh
from src.config import settings


@pytest.fixture
def client():
    with patch("src.db.get_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        with patch("src.db.init_schema", new_callable=AsyncMock):
            from src.api.main import app

            with TestClient(app) as c:
                yield c


class TestTickerDueForEarningsRefresh:
    @pytest.mark.asyncio
    async def test_not_due_when_no_analysis_exists(self):
        with patch("src.api.routes.scheduled.fetchrow", new_callable=AsyncMock) as mock_fetchrow:
            mock_fetchrow.return_value = None
            assert await _ticker_due_for_earnings_refresh("NVDA") is False

    @pytest.mark.asyncio
    async def test_not_due_when_no_earnings_date_recorded(self):
        with patch("src.api.routes.scheduled.fetchrow", new_callable=AsyncMock) as mock_fetchrow:
            mock_fetchrow.return_value = {"earnings": {}}
            assert await _ticker_due_for_earnings_refresh("NVDA") is False

    @pytest.mark.asyncio
    async def test_not_due_when_earnings_date_is_in_the_future(self):
        future = date.today() + timedelta(days=10)
        with patch("src.api.routes.scheduled.fetchrow", new_callable=AsyncMock) as mock_fetchrow:
            mock_fetchrow.return_value = {"earnings": {"next_earnings_date": str(future)}}
            assert await _ticker_due_for_earnings_refresh("NVDA") is False

    @pytest.mark.asyncio
    async def test_due_when_earnings_date_has_passed(self):
        past = date.today() - timedelta(days=2)
        with patch("src.api.routes.scheduled.fetchrow", new_callable=AsyncMock) as mock_fetchrow:
            mock_fetchrow.return_value = {"earnings": {"next_earnings_date": str(past)}}
            assert await _ticker_due_for_earnings_refresh("NVDA") is True

    @pytest.mark.asyncio
    async def test_handles_json_string_earnings_column(self):
        """asyncpg may return JSONB as a raw string depending on codec config."""
        past = date.today() - timedelta(days=2)
        with patch("src.api.routes.scheduled.fetchrow", new_callable=AsyncMock) as mock_fetchrow:
            mock_fetchrow.return_value = {"earnings": f'{{"next_earnings_date": "{past}"}}'}
            assert await _ticker_due_for_earnings_refresh("NVDA") is True

    @pytest.mark.asyncio
    async def test_not_due_on_malformed_date_string(self):
        with patch("src.api.routes.scheduled.fetchrow", new_callable=AsyncMock) as mock_fetchrow:
            mock_fetchrow.return_value = {"earnings": {"next_earnings_date": "not-a-date"}}
            assert await _ticker_due_for_earnings_refresh("NVDA") is False


class TestRefreshEarningsEndpoint:
    def test_requires_scheduler_token_configured(self, client):
        with patch.object(settings, "scheduler_secret_token", ""):
            response = client.post("/api/scheduled/refresh-earnings")
        assert response.status_code == 503

    def test_rejects_wrong_token(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            response = client.post(
                "/api/scheduled/refresh-earnings",
                headers={"x-scheduler-token": "wrong-token"},
            )
        assert response.status_code == 401

    def test_skips_when_portfolio_empty(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch(
                "src.api.routes.scheduled.fetch_all_positions",
                new_callable=AsyncMock,
                return_value=[],
            ):
                response = client.post(
                    "/api/scheduled/refresh-earnings",
                    headers={"x-scheduler-token": "correct-token"},
                )
        assert response.status_code == 200
        assert response.json()["status"] == "skipped"

    def test_skips_when_no_ticker_is_due(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch(
                "src.api.routes.scheduled.fetch_all_positions",
                new_callable=AsyncMock,
                return_value=[{"ticker": "NVDA"}],
            ):
                with patch(
                    "src.api.routes.scheduled._ticker_due_for_earnings_refresh",
                    new_callable=AsyncMock,
                    return_value=False,
                ):
                    response = client.post(
                        "/api/scheduled/refresh-earnings",
                        headers={"x-scheduler-token": "correct-token"},
                    )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"
        assert data["tickers"] == []

    def test_refreshes_only_due_tickers(self, client):
        from datetime import datetime, timezone

        from src.api.schemas import AnalyzeResponse

        async def _due_side_effect(ticker):
            return ticker == "NVDA"

        mock_response = AnalyzeResponse(
            id="test-id",
            tickers=["NVDA"],
            report_markdown="",
            analyses={},
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch(
                "src.api.routes.scheduled.fetch_all_positions",
                new_callable=AsyncMock,
                return_value=[{"ticker": "NVDA"}, {"ticker": "AAPL"}],
            ):
                with patch(
                    "src.api.routes.scheduled._ticker_due_for_earnings_refresh",
                    side_effect=_due_side_effect,
                ):
                    with patch(
                        "src.api.routes.scheduled.analyze_tickers",
                        new_callable=AsyncMock,
                        return_value=mock_response,
                    ) as mock_analyze:
                        response = client.post(
                            "/api/scheduled/refresh-earnings",
                            headers={"x-scheduler-token": "correct-token"},
                        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["tickers"] == ["NVDA"]
        mock_analyze.assert_awaited_once()
        called_tickers = mock_analyze.call_args[0][0]
        assert called_tickers == ["NVDA"]
