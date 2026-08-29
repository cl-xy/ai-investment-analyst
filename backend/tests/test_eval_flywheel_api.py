"""
Tests for Task 6: eval_flywheel read APIs and protected trigger endpoint.
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


class TestFunnelEndpoint:
    def test_returns_zeroed_funnel_when_no_data(self, client):
        with (
            patch("src.api.routes.eval_flywheel.fetchval", new_callable=AsyncMock, return_value=0),
            patch("src.api.routes.eval_flywheel.fetch", new_callable=AsyncMock, return_value=[]),
        ):
            response = client.get("/api/eval-flywheel/funnel")
        assert response.status_code == 200
        data = response.json()
        assert data["resolved_predictions"] == 0
        assert data["promotion_reasons"] == []

    def test_returns_populated_funnel(self, client):
        with (
            patch(
                "src.api.routes.eval_flywheel.fetchval",
                new_callable=AsyncMock,
                side_effect=[100, 20, 15, 12],
            ),
            patch(
                "src.api.routes.eval_flywheel.fetch",
                new_callable=AsyncMock,
                return_value=[{"reason": "high_confidence_incorrect", "count": 8}],
            ),
        ):
            response = client.get("/api/eval-flywheel/funnel")
        data = response.json()
        assert data["resolved_predictions"] == 100
        assert data["promoted_cases"] == 15
        assert data["promotion_reasons"][0]["count"] == 8


class TestListCasesEndpoint:
    def test_rejects_invalid_state_filter(self, client):
        response = client.get("/api/eval-flywheel/cases?state=not_a_state")
        assert response.status_code == 400

    def test_empty_case_list(self, client):
        with (
            patch("src.api.routes.eval_flywheel.fetch", new_callable=AsyncMock, return_value=[]),
            patch("src.api.routes.eval_flywheel.fetchval", new_callable=AsyncMock, return_value=0),
        ):
            response = client.get("/api/eval-flywheel/cases")
        assert response.status_code == 200
        data = response.json()
        assert data["cases"] == []
        assert data["total"] == 0

    def test_pagination_params_validated(self, client):
        response = client.get("/api/eval-flywheel/cases?limit=0")
        assert response.status_code == 422  # ge=1 violated

        response = client.get("/api/eval-flywheel/cases?limit=500")
        assert response.status_code == 422  # le=200 violated


class TestGetCaseDetailEndpoint:
    def test_404_when_case_missing(self, client):
        with patch(
            "src.api.routes.eval_flywheel.fetchrow", new_callable=AsyncMock, return_value=None
        ):
            response = client.get("/api/eval-flywheel/cases/nonexistent")
        assert response.status_code == 404


class TestListRunsEndpoint:
    def test_empty_run_history(self, client):
        with patch("src.api.routes.eval_flywheel.fetch", new_callable=AsyncMock, return_value=[]):
            response = client.get("/api/eval-flywheel/runs")
        assert response.status_code == 200
        assert response.json()["runs"] == []


class TestGetRunDetailEndpoint:
    def test_404_when_run_missing(self, client):
        with patch(
            "src.api.routes.eval_flywheel.fetchrow", new_callable=AsyncMock, return_value=None
        ):
            response = client.get("/api/eval-flywheel/runs/nonexistent")
        assert response.status_code == 404


class TestTriggerEndpointAuth:
    def test_missing_token_when_none_configured_returns_503(self, client):
        with patch("src.api.routes.eval_flywheel.settings") as mock_settings:
            mock_settings.scheduler_secret_token = ""
            response = client.post("/api/eval-flywheel/runs/trigger")
        assert response.status_code == 503

    def test_wrong_token_rejected(self, client):
        with patch("src.api.routes.eval_flywheel.settings") as mock_settings:
            mock_settings.scheduler_secret_token = "correct-token"
            response = client.post(
                "/api/eval-flywheel/runs/trigger",
                headers={"x-scheduler-token": "wrong-token"},
            )
        assert response.status_code == 401

    def test_correct_token_proceeds_to_runner(self, client):
        with (
            patch("src.api.routes.eval_flywheel.settings") as mock_settings,
            patch(
                "src.eval_flywheel.runner.run_bounded_evaluation",
                new_callable=AsyncMock,
                return_value={"run_id": "r1", "case_count": 0, "decision": "insufficient_data"},
            ),
        ):
            mock_settings.scheduler_secret_token = "correct-token"
            response = client.post(
                "/api/eval-flywheel/runs/trigger",
                headers={"x-scheduler-token": "correct-token"},
            )
        assert response.status_code == 200
        assert response.json()["decision"] == "insufficient_data"
