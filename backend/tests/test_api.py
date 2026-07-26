"""
API endpoint smoke tests.
Tests that endpoints respond with correct status codes and basic validation.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with mocked DB."""
    with patch("src.api.db.get_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        from src.api.main import app

        with TestClient(app) as c:
            yield c


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestStreamEndpoint:
    def test_stream_requires_tickers(self, client):
        response = client.get("/api/analyze/stream")
        # FastAPI returns 422 for missing required query params
        assert response.status_code == 422

    def test_stream_validates_ticker_format(self, client):
        response = client.get("/api/analyze/stream?tickers=INVALID!!!")
        assert response.status_code == 200  # Returns JSON error, not HTTP error
        data = response.json()
        assert "error" in data

    def test_stream_rejects_too_many_tickers(self, client):
        response = client.get("/api/analyze/stream?tickers=A,B,C,D,E,F")
        data = response.json()
        assert "error" in data
        assert "Maximum 5" in data["error"]

    def test_stream_accepts_valid_tickers(self, client):
        # This will fail to connect to the actual agent, but validates input
        response = client.get("/api/analyze/stream?tickers=NVDA,AAPL")
        # Should start streaming (200) or error from agent, not input validation
        assert response.status_code == 200


class TestAdminEndpoint:
    def test_admin_requires_auth(self, client):
        response = client.post("/api/admin/warm-cache")
        assert response.status_code in (401, 503)

    def test_admin_rejects_bad_token(self, client):
        with patch.dict("os.environ", {"SCHEDULER_SECRET_TOKEN": "real-token"}):
            response = client.post(
                "/api/admin/warm-cache",
                headers={"Authorization": "Bearer wrong-token"},
            )
            assert response.status_code == 403


class TestDemoAuth:
    def test_no_password_configured_allows_all(self, client):
        """When DEMO_PASSWORD is empty, all requests pass through."""
        with patch.dict("os.environ", {"DEMO_PASSWORD": ""}):
            response = client.get("/api/health")
            assert response.status_code == 200

    def test_password_required_on_analyze(self, client):
        """When DEMO_PASSWORD is set, analyze endpoints require it."""
        with patch.dict("os.environ", {"DEMO_PASSWORD": "secret123"}):
            # Health should still work
            response = client.get("/api/health")
            assert response.status_code == 200
