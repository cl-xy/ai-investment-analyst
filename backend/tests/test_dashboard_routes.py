"""
Tests for the /api/dashboard routes.

Regression coverage for the "Network error" bug on History -> Past Analyses:
asyncpg returns JSONB columns (risk_flags, price_data, fundamentals, earnings)
as raw JSON text (str) rather than list/dict when no type codec is registered
on the connection. dashboard.py::get_analysis previously passed those raw
strings straight into TickerAnalysis(...), causing a 4-field Pydantic
ValidationError that FastAPI surfaced as a 500 (seen client-side as a
network error).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("src.db.get_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        with patch("src.db.init_schema", new_callable=AsyncMock):
            from src.api.main import app

            with TestClient(app) as c:
                yield c


def _fake_analysis_row(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        tickers=["AAPL"],
        report_markdown="# Report",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return defaults


def _fake_ticker_row_as_strings(**overrides):
    """Replicates exactly what asyncpg returns for JSONB columns when no
    type codec is registered: risk_flags/price_data/fundamentals/earnings
    come back as raw JSON text, not decoded Python objects."""
    defaults = dict(
        ticker="AAPL",
        signal="buy",
        confidence="high",
        sentiment_score=0.42,
        news_summary="Strong quarter.",
        risk_flags='["Margin compression from rising input costs", "Regulatory scrutiny limiting further upside."]',
        price_data='{"ticker": "AAPL", "volume": 5000000, "fifty_two_week_high": null}',
        fundamentals='{"eps": 8.25, "beta": 1.2, "revenue_growth_yoy": 0.166}',
        earnings="{}",
        sec_notes="",
    )
    defaults.update(overrides)
    return defaults


def _fake_ticker_row_as_decoded(**overrides):
    """The already-decoded shape (e.g. if a codec were registered)."""
    defaults = dict(
        ticker="AAPL",
        signal="buy",
        confidence="high",
        sentiment_score=0.42,
        news_summary="Strong quarter.",
        risk_flags=["Margin compression from rising input costs"],
        price_data={"ticker": "AAPL", "volume": 5000000},
        fundamentals={"eps": 8.25, "beta": 1.2},
        earnings={},
        sec_notes="",
    )
    defaults.update(overrides)
    return defaults


class TestGetAnalysis:
    def test_returns_200_when_jsonb_columns_are_raw_strings(self, client):
        """Reproduces the exact bug from production fly logs: JSONB columns
        returned as strings by asyncpg must be coerced, not passed through
        raw into the TickerAnalysis pydantic model."""
        analysis_id = str(uuid.uuid4())
        analysis_row = _fake_analysis_row(id=uuid.UUID(analysis_id))
        ticker_row = _fake_ticker_row_as_strings()

        async def _fake_fetchrow(query, *args):
            return analysis_row

        with (
            patch("src.api.routes.dashboard.fetchrow", side_effect=_fake_fetchrow),
            patch(
                "src.api.routes.dashboard.fetch",
                new=AsyncMock(return_value=[ticker_row]),
            ),
        ):
            response = client.get(f"/api/dashboard/{analysis_id}")

        assert response.status_code == 200
        data = response.json()
        analysis = data["analyses"]["AAPL"]
        assert isinstance(analysis["risk_flags"], list)
        assert analysis["risk_flags"] == [
            "Margin compression from rising input costs",
            "Regulatory scrutiny limiting further upside.",
        ]
        assert isinstance(analysis["price_data"], dict)
        assert analysis["price_data"]["ticker"] == "AAPL"
        assert isinstance(analysis["fundamentals"], dict)
        assert analysis["fundamentals"]["eps"] == 8.25
        assert isinstance(analysis["earnings"], dict)
        assert analysis["earnings"] == {}

    def test_returns_200_when_jsonb_columns_already_decoded(self, client):
        """If a type codec is ever registered upstream and asyncpg returns
        already-decoded list/dict values, the route must still work
        (passthrough, not double-decode)."""
        analysis_id = str(uuid.uuid4())
        analysis_row = _fake_analysis_row(id=uuid.UUID(analysis_id))
        ticker_row = _fake_ticker_row_as_decoded()

        async def _fake_fetchrow(query, *args):
            return analysis_row

        with (
            patch("src.api.routes.dashboard.fetchrow", side_effect=_fake_fetchrow),
            patch(
                "src.api.routes.dashboard.fetch",
                new=AsyncMock(return_value=[ticker_row]),
            ),
        ):
            response = client.get(f"/api/dashboard/{analysis_id}")

        assert response.status_code == 200
        analysis = response.json()["analyses"]["AAPL"]
        assert analysis["risk_flags"] == ["Margin compression from rising input costs"]
        assert analysis["price_data"]["volume"] == 5000000

    def test_invalid_uuid_returns_400(self, client):
        response = client.get("/api/dashboard/not-a-uuid")
        assert response.status_code == 400

    def test_missing_analysis_returns_404(self, client):
        with patch("src.api.routes.dashboard.fetchrow", new=AsyncMock(return_value=None)):
            response = client.get(f"/api/dashboard/{uuid.uuid4()}")
        assert response.status_code == 404
