"""
Tests for the compare endpoint.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with mocked DB."""
    with patch("src.api.db.get_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        with patch("src.api.db.init_schema", new_callable=AsyncMock):
            from src.api.main import app

            with TestClient(app) as c:
                yield c


class TestCompareEndpoint:
    def test_compare_requires_at_least_2_tickers(self, client):
        response = client.get("/api/compare?tickers=NVDA")
        assert response.status_code == 400
        assert "At least 2" in response.json()["detail"]

    def test_compare_rejects_more_than_3_tickers(self, client):
        response = client.get("/api/compare?tickers=A,B,C,D")
        assert response.status_code == 400
        assert "Maximum 3" in response.json()["detail"]

    def test_compare_requires_tickers_param(self, client):
        response = client.get("/api/compare")
        assert response.status_code == 422  # Missing required query param

    @patch("src.api.routes.compare.analyze_tickers")
    def test_compare_returns_analyses(self, mock_analyze, client):
        """Compare endpoint should return analyses for valid tickers."""
        from datetime import datetime, timezone

        from src.api.schemas import AnalyzeResponse, TickerAnalysis

        mock_analysis = TickerAnalysis(
            ticker="NVDA",
            signal="buy",
            confidence="high",
            sentiment_score=0.8,
            news_summary="Strong",
            risk_flags=["Valuation"],
            price_data={"price": 875},
            fundamentals={},
            sec_notes="",
        )
        mock_analyze.return_value = AnalyzeResponse(
            id="test-id",
            tickers=["NVDA", "AAPL"],
            report_markdown="",
            analyses={"NVDA": mock_analysis, "AAPL": mock_analysis},
            created_at=datetime.now(timezone.utc),
        )

        response = client.get("/api/compare?tickers=NVDA,AAPL")
        assert response.status_code == 200
        data = response.json()
        assert data["tickers"] == ["NVDA", "AAPL"]
        assert "NVDA" in data["analyses"]
        assert "AAPL" in data["analyses"]
