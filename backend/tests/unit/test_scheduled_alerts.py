"""Unit tests for the POST /api/scheduled/evaluate-alerts endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.alerts.pipeline import PipelineRunSummary
from src.config import settings


@pytest.fixture
def client():
    with patch("src.db.get_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        with patch("src.db.init_schema", new_callable=AsyncMock):
            from src.api.main import app

            with TestClient(app) as c:
                yield c


class TestEvaluateAlertsAuth:
    def test_requires_scheduler_token_configured(self, client):
        with patch.object(settings, "scheduler_secret_token", ""):
            response = client.post("/api/scheduled/evaluate-alerts")
        assert response.status_code == 503

    def test_rejects_missing_token(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            response = client.post("/api/scheduled/evaluate-alerts")
        assert response.status_code == 401

    def test_rejects_wrong_token(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            response = client.post(
                "/api/scheduled/evaluate-alerts",
                headers={"x-scheduler-token": "wrong-token"},
            )
        assert response.status_code == 401


class TestEvaluateAlertsSuccess:
    def test_returns_summary_on_success(self, client):
        summary = PipelineRunSummary(
            tickers_evaluated=3, alerts_fired=1, llm_calls_used=1, heuristic_only_count=0
        )
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch(
                "src.api.routes.scheduled.evaluate_all_monitored",
                new=AsyncMock(return_value=summary),
            ):
                response = client.post(
                    "/api/scheduled/evaluate-alerts",
                    headers={"x-scheduler-token": "correct-token"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["tickers_evaluated"] == 3
        assert data["alerts_fired"] == 1

    def test_slot_unavailable_skips(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch(
                "src.api.routes.scheduled.acquire_analysis_slot",
                new=AsyncMock(return_value=False),
            ):
                response = client.post(
                    "/api/scheduled/evaluate-alerts",
                    headers={"x-scheduler-token": "correct-token"},
                )

        assert response.status_code == 200
        assert response.json()["status"] == "skipped"

    def test_timeout_reports_failed(self, client):
        import asyncio

        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch(
                "src.api.routes.scheduled.evaluate_all_monitored",
                new=AsyncMock(side_effect=asyncio.TimeoutError()),
            ):
                response = client.post(
                    "/api/scheduled/evaluate-alerts",
                    headers={"x-scheduler-token": "correct-token"},
                )

        assert response.status_code == 200
        assert response.json()["status"] == "failed"

    def test_unexpected_exception_reports_failed(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch(
                "src.api.routes.scheduled.evaluate_all_monitored",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ):
                response = client.post(
                    "/api/scheduled/evaluate-alerts",
                    headers={"x-scheduler-token": "correct-token"},
                )

        assert response.status_code == 200
        assert response.json()["status"] == "failed"

    def test_concurrent_call_is_skipped_by_lock(self, client):
        """Simulate the lock already being held (mirrors the pattern used for
        refresh-portfolio/refresh-earnings concurrency guards)."""
        from src.api.routes import scheduled as scheduled_module

        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch.object(scheduled_module._ALERT_EVAL_LOCK, "locked", return_value=True):
                response = client.post(
                    "/api/scheduled/evaluate-alerts",
                    headers={"x-scheduler-token": "correct-token"},
                )

        assert response.status_code == 200
        assert response.json()["status"] == "skipped"


class TestRefreshPortfolioAlertHook:
    """The refresh-portfolio endpoint should fire a best-effort background
    alert evaluation on success, without blocking its own response."""

    def test_successful_refresh_schedules_background_evaluation(self, client):
        import asyncio
        from datetime import datetime, timezone

        from src.api.schemas import AnalyzeResponse

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
                new=AsyncMock(return_value=[{"ticker": "NVDA"}]),
            ):
                with patch(
                    "src.api.routes.scheduled.analyze_tickers",
                    new=AsyncMock(return_value=mock_response),
                ):
                    with patch(
                        "src.api.routes.scheduled.asyncio.create_task"
                    ) as mock_create_task:
                        response = client.post(
                            "/api/scheduled/refresh-portfolio",
                            headers={"x-scheduler-token": "correct-token"},
                        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        mock_create_task.assert_called_once()
        # Close the un-awaited coroutine passed to the mocked create_task to
        # avoid a "coroutine was never awaited" resource warning.
        passed_coro = mock_create_task.call_args.args[0]
        passed_coro.close()

    @pytest.mark.asyncio
    async def test_best_effort_hook_swallows_exceptions(self):
        from src.api.routes.scheduled import _evaluate_alerts_best_effort

        with patch(
            "src.alerts.pipeline.evaluate_all_monitored",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            # Should not raise
            await _evaluate_alerts_best_effort()
