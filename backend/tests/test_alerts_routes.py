"""
Tests for the /api/alerts routes (history, unread count, acknowledge,
watchlist subscriptions).
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


def _fake_alert_row(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        ticker="NVDA",
        alert_type="sentiment",
        severity="critical",
        drift_score=0.65,
        old_signal="buy",
        new_signal="hold",
        reasoning_diff={"prior_signal": "buy"},
        triggered_by=["sentiment"],
        llm_judged=True,
        dispatched_telegram=True,
        created_at=datetime.now(timezone.utc),
        acknowledged_at=None,
    )
    defaults.update(overrides)
    return defaults


class TestListAlerts:
    def test_returns_paginated_alerts(self, client):
        rows = [_fake_alert_row()]
        with (
            patch("src.api.routes.alerts.fetch", new=AsyncMock(return_value=rows)),
            patch("src.api.routes.alerts.fetchval", new=AsyncMock(return_value=1)),
        ):
            response = client.get("/api/alerts")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["alerts"][0]["ticker"] == "NVDA"

    def test_filters_by_ticker(self, client):
        with (
            patch("src.api.routes.alerts.fetch", new=AsyncMock(return_value=[])) as mock_fetch,
            patch("src.api.routes.alerts.fetchval", new=AsyncMock(return_value=0)),
        ):
            response = client.get("/api/alerts", params={"ticker": "nvda"})

        assert response.status_code == 200
        # Ensure ticker was normalized to uppercase in the query params
        args = mock_fetch.call_args.args
        assert "NVDA" in args


class TestUnreadCount:
    def test_returns_count(self, client):
        with patch("src.api.routes.alerts.fetchval", new=AsyncMock(return_value=3)):
            response = client.get("/api/alerts/unread-count")
        assert response.status_code == 200
        assert response.json()["unread_count"] == 3

    def test_zero_when_none_returned(self, client):
        with patch("src.api.routes.alerts.fetchval", new=AsyncMock(return_value=None)):
            response = client.get("/api/alerts/unread-count")
        assert response.json()["unread_count"] == 0


class TestAcknowledgeAlert:
    def test_acknowledges_unread_alert(self, client):
        alert_id = str(uuid.uuid4())
        row = _fake_alert_row(id=uuid.UUID(alert_id), acknowledged_at=datetime.now(timezone.utc))
        with patch("src.api.routes.alerts.fetch", new=AsyncMock(return_value=[row])):
            response = client.post(f"/api/alerts/{alert_id}/acknowledge")
        assert response.status_code == 200
        assert response.json()["acknowledged_at"] is not None

    def test_invalid_uuid_returns_400(self, client):
        response = client.post("/api/alerts/not-a-uuid/acknowledge")
        assert response.status_code == 400

    def test_missing_alert_returns_404(self, client):
        with (
            patch("src.api.routes.alerts.fetch", new=AsyncMock(return_value=[])),
        ):
            response = client.post(f"/api/alerts/{uuid.uuid4()}/acknowledge")
        assert response.status_code == 404

    def test_already_acknowledged_returns_existing(self, client):
        alert_id = str(uuid.uuid4())
        already_ack = _fake_alert_row(
            id=uuid.UUID(alert_id), acknowledged_at=datetime.now(timezone.utc)
        )

        call_count = 0

        async def _fake_fetch(query, *args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []  # UPDATE ... RETURNING found no unacknowledged row
            return [already_ack]

        with patch("src.api.routes.alerts.fetch", side_effect=_fake_fetch):
            response = client.post(f"/api/alerts/{alert_id}/acknowledge")

        assert response.status_code == 200


class TestSubscriptions:
    def test_list_subscriptions(self, client):
        from src.alerts.subscriptions import AlertSubscription

        subs = [AlertSubscription(ticker="AAPL", source="watchlist", trigger_types=["price"], active=True)]
        with patch("src.api.routes.alerts.list_subscriptions", new=AsyncMock(return_value=subs)):
            response = client.get("/api/alerts/subscriptions")
        assert response.status_code == 200
        assert response.json()["subscriptions"][0]["ticker"] == "AAPL"

    def test_create_subscription(self, client):
        from src.alerts.subscriptions import AlertSubscription

        result = AlertSubscription(
            ticker="TSLA", source="watchlist", trigger_types=["sec", "price"], active=True
        )
        with patch("src.api.routes.alerts.subscribe_ticker", new=AsyncMock(return_value=result)):
            response = client.post("/api/alerts/subscribe", json={"ticker": "tsla"})
        assert response.status_code == 200
        assert response.json()["ticker"] == "TSLA"

    def test_create_subscription_rejects_invalid_ticker(self, client):
        response = client.post("/api/alerts/subscribe", json={"ticker": "!!!invalid!!!"})
        assert response.status_code == 422

    def test_delete_subscription_success(self, client):
        with patch("src.api.routes.alerts.unsubscribe_ticker", new=AsyncMock(return_value=True)):
            response = client.delete("/api/alerts/subscribe/TSLA")
        assert response.status_code == 204

    def test_delete_subscription_not_found(self, client):
        with patch("src.api.routes.alerts.unsubscribe_ticker", new=AsyncMock(return_value=False)):
            response = client.delete("/api/alerts/subscribe/TSLA")
        assert response.status_code == 404


class TestDemoAuthGating:
    def test_alerts_endpoint_requires_password_when_configured(self, client):
        from src.middleware import auth as auth_module

        with patch.object(auth_module, "_DEMO_PASSWORD", "secret123"):
            response = client.get("/api/alerts")
        assert response.status_code == 401

    def test_alerts_endpoint_accepts_correct_password(self, client):
        from src.middleware import auth as auth_module

        with patch.object(auth_module, "_DEMO_PASSWORD", "secret123"):
            with (
                patch("src.api.routes.alerts.fetch", new=AsyncMock(return_value=[])),
                patch("src.api.routes.alerts.fetchval", new=AsyncMock(return_value=0)),
            ):
                response = client.get("/api/alerts", params={"password": "secret123"})
        assert response.status_code == 200
