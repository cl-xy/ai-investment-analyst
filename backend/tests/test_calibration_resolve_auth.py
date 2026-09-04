"""
Task 7: deterministic auth tests for the scheduler-token gate added to
/api/calibration/resolve. Zero LLM calls, zero live network calls — pure
HTTP-layer auth verification, matching the pattern already used for
routes/scheduled.py's endpoints.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("src.db.get_pool", new_callable=AsyncMock):
        with patch("src.db.init_schema", new_callable=AsyncMock):
            from src.api.main import app

            with TestClient(app) as c:
                yield c


class TestCalibrationResolveSchedulerAuth:
    def test_no_token_configured_returns_503(self, client):
        with patch("src.api.routes.calibration.settings") as mock_settings:
            mock_settings.scheduler_secret_token = ""
            response = client.post("/api/calibration/resolve")
        assert response.status_code == 503

    def test_missing_header_returns_401(self, client):
        with patch("src.api.routes.calibration.settings") as mock_settings:
            mock_settings.scheduler_secret_token = "correct-token"  # pragma: allowlist secret
            response = client.post("/api/calibration/resolve")
        assert response.status_code == 401

    def test_wrong_token_returns_401(self, client):
        with patch("src.api.routes.calibration.settings") as mock_settings:
            mock_settings.scheduler_secret_token = "correct-token"  # pragma: allowlist secret
            response = client.post(
                "/api/calibration/resolve",
                headers={"x-scheduler-token": "wrong-token"},
            )
        assert response.status_code == 401

    def test_correct_token_proceeds_past_auth(self, client):
        with (
            patch("src.api.routes.calibration.settings") as mock_settings,
            patch("src.db.get_pool", new_callable=AsyncMock) as mock_get_pool,
        ):
            mock_settings.scheduler_secret_token = "correct-token"  # pragma: allowlist secret

            mock_conn = AsyncMock()
            mock_conn.fetch = AsyncMock(return_value=[])

            class _Ctx:
                async def __aenter__(self):
                    return mock_conn

                async def __aexit__(self, *exc):
                    return False

            mock_conn.transaction = lambda: _Ctx()
            mock_pool = AsyncMock()
            mock_pool.acquire = lambda: _Ctx2(mock_conn)
            mock_get_pool.return_value = mock_pool

            response = client.post(
                "/api/calibration/resolve",
                headers={"x-scheduler-token": "correct-token"},
            )
        # Reaches the "no predictions ready" branch rather than 401/503.
        assert response.status_code == 200
        assert response.json()["resolved_count"] == 0


class _Ctx2:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False
