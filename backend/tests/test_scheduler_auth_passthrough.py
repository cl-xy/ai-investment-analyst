"""The demo-password gate must not block scheduler-token endpoints.

GitHub Actions calls /api/calibration/resolve and /api/eval-flywheel/runs/trigger
with only an x-scheduler-token header. Those routes check the token themselves,
so the middleware has to hand them through. The route tests elsewhere run with the
demo gate switched off, which is how this went unnoticed; these set it on.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

DEMO = "demo-secret"  # pragma: allowlist secret
SCHEDULER = "scheduler-secret"  # pragma: allowlist secret


@pytest.fixture
def client():
    with patch("src.db.get_pool", new_callable=AsyncMock):
        with patch("src.db.init_schema", new_callable=AsyncMock):
            from src.api.main import app

            with TestClient(app) as c:
                yield c


@pytest.fixture(autouse=True)
def _gate_on():
    with (
        patch("src.middleware.auth._DEMO_PASSWORD", DEMO),
        patch("src.api.routes.calibration.settings") as cal_settings,
        patch("src.api.routes.eval_flywheel.settings") as fly_settings,
    ):
        cal_settings.scheduler_secret_token = SCHEDULER
        fly_settings.scheduler_secret_token = SCHEDULER
        yield


def _detail(response) -> str:
    return response.json().get("detail", "")


@pytest.mark.parametrize("path", ["/api/calibration/resolve", "/api/eval-flywheel/runs/trigger"])
def test_scheduler_header_reaches_the_route_check(client, path):
    # A wrong token gets the route's own 401, not the demo-password message.
    response = client.post(path, headers={"x-scheduler-token": "wrong"})
    assert response.status_code == 401
    assert _detail(response) == "Unauthorized scheduler request"


@pytest.mark.parametrize("path", ["/api/calibration/resolve", "/api/eval-flywheel/runs/trigger"])
def test_without_scheduler_header_the_demo_gate_still_applies(client, path):
    response = client.post(path)
    assert response.status_code == 401
    assert "Demo password required" in _detail(response)


def test_valid_scheduler_token_is_accepted_end_to_end(client):
    with patch(
        "src.eval_flywheel.runner.run_bounded_evaluation",
        new_callable=AsyncMock,
        return_value={"run_id": "r1", "case_count": 0, "decision": "insufficient_data"},
    ):
        response = client.post(
            "/api/eval-flywheel/runs/trigger", headers={"x-scheduler-token": SCHEDULER}
        )
    assert response.status_code == 200
    assert response.json()["decision"] == "insufficient_data"


def test_header_does_not_open_other_protected_paths(client):
    response = client.get("/api/calibration", headers={"x-scheduler-token": SCHEDULER})
    assert response.status_code == 401
    assert "Demo password required" in _detail(response)

    response = client.post("/api/analyze", headers={"x-scheduler-token": SCHEDULER})
    assert response.status_code == 401
    assert "Demo password required" in _detail(response)


def test_header_only_applies_to_post(client):
    response = client.get("/api/calibration/resolve", headers={"x-scheduler-token": SCHEDULER})
    assert response.status_code == 401
    assert "Demo password required" in _detail(response)


def test_empty_scheduler_header_does_not_bypass_the_gate(client):
    response = client.post("/api/calibration/resolve", headers={"x-scheduler-token": ""})
    assert response.status_code == 401
    assert "Demo password required" in _detail(response)


def test_demo_password_still_works_for_normal_users(client):
    # Past the gate means no demo-password rejection. What the route does next
    # (it hits the mocked DB here) is not this test's concern.
    try:
        response = client.get("/api/calibration", headers={"X-Demo-Password": DEMO})
    except Exception:
        return  # request reached the route and failed there, so auth let it through
    assert "Demo password required" not in response.text
