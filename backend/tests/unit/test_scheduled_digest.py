"""Unit tests for the POST /api/scheduled/send-digest endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.config import settings


@pytest.fixture
def client():
    with patch("src.db.get_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        with patch("src.db.init_schema", new_callable=AsyncMock):
            from src.api.main import app

            with TestClient(app) as c:
                yield c


class TestSendDigestAuth:
    def test_requires_scheduler_token_configured(self, client):
        with patch.object(settings, "scheduler_secret_token", ""):
            response = client.post("/api/scheduled/send-digest")
        assert response.status_code == 503

    def test_rejects_missing_token(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            response = client.post("/api/scheduled/send-digest")
        assert response.status_code == 401

    def test_rejects_wrong_token(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            response = client.post(
                "/api/scheduled/send-digest",
                headers={"x-scheduler-token": "wrong-token"},
            )
        assert response.status_code == 401


class TestSendDigestSuccess:
    def test_returns_skipped_when_no_monitored_tickers(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch(
                "src.alerts.pipeline.get_monitored_tickers", new=AsyncMock(return_value=[])
            ):
                with patch(
                    "src.alerts.composer.get_recent_alerts", new=AsyncMock(return_value=[])
                ):
                    response = client.post(
                        "/api/scheduled/send-digest",
                        headers={"x-scheduler-token": "correct-token"},
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"
        assert data["tickers_included"] == 0

    def test_returns_success_and_dispatches_to_active_chats(self, client):
        from src.alerts.last_analysis import LastAnalysisSnapshot
        from datetime import datetime, timezone

        snapshot = LastAnalysisSnapshot(
            ticker="NVDA",
            signal="buy",
            confidence="high",
            sentiment_score=0.5,
            risk_flags=[],
            price_data={},
            fundamentals={},
            analysis_id="11111111-1111-1111-1111-111111111111",
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with (
                patch(
                    "src.alerts.pipeline.get_monitored_tickers",
                    new=AsyncMock(return_value=["NVDA"]),
                ),
                patch(
                    "src.alerts.last_analysis.get_last_analysis",
                    new=AsyncMock(return_value=snapshot),
                ),
                patch(
                    "src.alerts.composer.get_recent_alerts", new=AsyncMock(return_value=[])
                ),
                patch(
                    "src.alerts.telegram.get_active_chat_ids",
                    new=AsyncMock(return_value=[111, 222]),
                ),
                patch(
                    "src.alerts.telegram._call_telegram",
                    new=AsyncMock(return_value={"ok": True}),
                ) as mock_call,
            ):
                response = client.post(
                    "/api/scheduled/send-digest",
                    headers={"x-scheduler-token": "correct-token"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["tickers_included"] == 1
        assert data["sent_to"] == 2
        assert mock_call.call_count == 2

    def test_timeout_reports_failed(self, client):
        import asyncio

        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch(
                "src.alerts.pipeline.get_monitored_tickers",
                new=AsyncMock(side_effect=asyncio.TimeoutError()),
            ):
                response = client.post(
                    "/api/scheduled/send-digest",
                    headers={"x-scheduler-token": "correct-token"},
                )

        assert response.status_code == 200
        assert response.json()["status"] == "failed"

    def test_unexpected_exception_reports_failed(self, client):
        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch(
                "src.alerts.pipeline.get_monitored_tickers",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ):
                response = client.post(
                    "/api/scheduled/send-digest",
                    headers={"x-scheduler-token": "correct-token"},
                )

        assert response.status_code == 200
        assert response.json()["status"] == "failed"

    def test_concurrent_call_is_skipped_by_lock(self, client):
        """Mirrors the lock-held guard pattern used for evaluate-alerts."""
        from src.api.routes import scheduled as scheduled_module

        with patch.object(settings, "scheduler_secret_token", "correct-token"):
            with patch.object(scheduled_module._DIGEST_LOCK, "locked", return_value=True):
                response = client.post(
                    "/api/scheduled/send-digest",
                    headers={"x-scheduler-token": "correct-token"},
                )

        assert response.status_code == 200
        assert response.json()["status"] == "skipped"
