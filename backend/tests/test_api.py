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
    with patch("src.db.get_pool") as mock_pool:
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
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_stream_rejects_too_many_tickers(self, client):
        response = client.get("/api/analyze/stream?tickers=A,B,C,D,E,F")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Maximum 4" in data["detail"]

    def test_stream_accepts_valid_tickers(self, client):
        # This will fail to connect to the actual agent, but validates input
        response = client.get("/api/analyze/stream?tickers=NVDA,AAPL")
        # Should start streaming (200) or error from agent, not input validation
        assert response.status_code == 200


class TestAdminEndpoint:
    def test_admin_requires_auth(self, client):
        response = client.get("/api/admin/budget")
        assert response.status_code in (401, 503)

    def test_admin_rejects_bad_token(self, client):
        with patch.dict("os.environ", {"SCHEDULER_SECRET_TOKEN": "real-token"}):
            response = client.get(
                "/api/admin/budget",
                headers={"Authorization": "Bearer wrong-token"},
            )
            assert response.status_code == 403


class TestDemoAuth:
    def test_explicit_disabled_mode_allows_requests(self, client):
        with patch("src.middleware.auth.settings.auth_mode", "disabled"):
            response = client.get("/api/analyze/stream")
            assert response.status_code == 422  # Reached route validation

    def test_password_required_on_analyze(self, client):
        with (
            patch("src.middleware.auth.settings.auth_mode", "demo"),
            patch("src.middleware.auth.settings.demo_password", "secret123"),
        ):
            assert client.get("/api/analyze/stream").status_code == 401
            assert client.get("/api/health").status_code == 200


class TestLoginEndpoint:
    def test_login_with_default_credentials_succeeds(self, client):
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "investor2026"},  # pragma: allowlist secret
        )
        assert response.status_code == 200
        assert "token" in response.json()

    def test_login_with_wrong_password_fails(self, client):
        response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert response.status_code == 401

    def test_login_with_wrong_username_fails(self, client):
        response = client.post(
            "/api/auth/login",
            json={
                "username": "someone-else",
                "password": "investor2026",  # pragma: allowlist secret
            },
        )
        assert response.status_code == 401

    def test_session_token_accepted_on_protected_route(self, client):
        with patch("src.middleware.auth.settings.auth_mode", "session"):
            login_response = client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "investor2026"},  # pragma: allowlist secret
            )
            token = login_response.json()["token"]

            response = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code != 401

    def test_invalid_session_token_rejected_on_protected_route(self, client):
        with patch("src.middleware.auth.settings.auth_mode", "session"):
            response = client.get(
                "/api/dashboard", headers={"Authorization": "Bearer not-a-real-token"}
            )
            assert response.status_code == 401
