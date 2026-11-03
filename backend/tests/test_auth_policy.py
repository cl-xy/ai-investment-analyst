"""Authentication policy, token integrity, and production startup regressions."""

import base64
import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.api.routes.auth import router
from src.config import Settings, settings
from src.middleware.auth import DemoAuthMiddleware, create_session_token, verify_session_token


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "session")
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "local-test-password")
    monkeypatch.setattr(settings, "session_signing_secret", "test-signing-key-" * 3)
    monkeypatch.setattr(settings, "demo_password", "")
    app = FastAPI()
    app.add_middleware(DemoAuthMiddleware)
    app.include_router(router, prefix="/api")

    @app.get("/api/dashboard")
    async def protected():
        return {"ok": True}

    @app.get("/api/health")
    async def public():
        return {"ok": True}

    @app.post("/api/ops/chaos")
    async def chaos(request: Request):
        from src.api.routes.ops import _check_ops_auth

        return {"authenticated": _check_ops_auth(request)}

    with TestClient(app) as test_client:
        yield test_client


def test_session_mode_protects_api_without_demo_password(client):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.options("/api/dashboard").status_code != 401


def test_login_token_works_for_api_and_ops(client):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "local-test-password"}
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['token']}"}
    assert client.get("/api/dashboard", headers=headers).status_code == 200
    assert client.post("/api/ops/chaos", headers=headers).json() == {"authenticated": True}


@pytest.mark.parametrize("credentials", [{"X-Demo-Password": "legacy"}, {}])
def test_session_mode_ignores_configured_demo_password(client, monkeypatch, credentials):
    monkeypatch.setattr(settings, "demo_password", "legacy")
    assert client.get("/api/dashboard", headers=credentials).status_code == 401
    assert client.get("/api/dashboard?password=legacy").status_code == 401


def test_demo_mode_requires_credentials_and_accepts_sessions(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "demo")
    monkeypatch.setattr(settings, "demo_password", "legacy")
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard", headers={"X-Demo-Password": "wrong"}).status_code == 401
    assert client.get("/api/dashboard", headers={"X-Demo-Password": "legacy"}).status_code == 200
    assert client.get("/api/dashboard?password=legacy").status_code == 200
    token = create_session_token("admin")
    assert (
        client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"}).status_code
        == 200
    )


def test_disabled_mode_is_explicit(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    assert client.get("/api/dashboard").status_code == 200


@pytest.mark.parametrize(
    "token",
    [
        "garbage",
        "====",
        "",
        base64.urlsafe_b64encode(b"a:b:c").decode(),
        base64.urlsafe_b64encode("admin:9999999999:☃".encode()).decode(),
    ],
)
def test_malformed_tokens_return_401(client, token):
    assert (
        client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_expiry_tampering_wrong_user_and_key_rotation(client, monkeypatch):
    with patch("src.middleware.auth.time.time", return_value=1000):
        token = create_session_token("admin")
        wrong_user = create_session_token("someone-else")
        assert verify_session_token(token)
        assert not verify_session_token(wrong_user)
        payload = base64.urlsafe_b64decode(token).decode().replace("admin:", "other:")
        assert not verify_session_token(base64.urlsafe_b64encode(payload.encode()).decode())
    with patch("src.middleware.auth.time.time", return_value=1000 + 86400):
        assert not verify_session_token(token)
    with patch("src.middleware.auth.time.time", return_value=1000):
        monkeypatch.setattr(settings, "session_signing_secret", "rotated-signing-key-" * 3)
        assert not verify_session_token(token)


def test_admin_password_cannot_sign_tokens(client):
    payload = "admin:9999999999"
    signature = hmac.new(
        settings.admin_password.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    forged = base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()
    assert not verify_session_token(forged)


def test_non_ascii_token_rejected(client):
    assert not verify_session_token("☃")


def production_settings(**overrides):
    values = dict(
        environment="production",
        auth_mode="session",
        admin_username="admin",
        admin_password="deployment-password",
        session_signing_secret="random-test-key-" * 3,
        demo_password="",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"auth_mode": "disabled"}, "disabled"),
        ({"admin_username": " "}, "ADMIN_USERNAME"),
        ({"admin_password": ""}, "ADMIN_PASSWORD"),
        ({"admin_password": "investor2026"}, "default ADMIN_PASSWORD"),
        ({"session_signing_secret": ""}, "SESSION_SIGNING_SECRET"),
        ({"session_signing_secret": "short"}, "SESSION_SIGNING_SECRET"),
        (
            {"admin_password": "same-secret-" * 4, "session_signing_secret": "same-secret-" * 4},
            "must differ",
        ),
        (
            {"demo_password": "same-secret-" * 4, "session_signing_secret": "same-secret-" * 4},
            "must differ",
        ),
        ({"auth_mode": "demo", "demo_password": " "}, "DEMO_PASSWORD"),
    ],
)
def test_unsafe_production_settings_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        production_settings(**overrides).validate_auth()


def test_valid_production_modes():
    production_settings().validate_auth()
    production_settings(auth_mode="demo", demo_password="legacy-demo-password").validate_auth()


def test_fly_deployment_cannot_bypass_production_validation(monkeypatch):
    monkeypatch.setenv("FLY_APP_NAME", "test-app")
    with pytest.raises(ValueError, match="disabled"):
        production_settings(environment="development", auth_mode="disabled").validate_auth()


def test_development_can_explicitly_disable_auth(monkeypatch):
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    production_settings(environment="development", auth_mode="disabled").validate_auth()


def test_settings_default_to_session(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    assert Settings(_env_file=None).auth_mode == "session"


@pytest.mark.asyncio
async def test_startup_rejects_unsafe_auth_before_database_access(monkeypatch):
    from src.api.main import _lifespan, app

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    with patch("src.api.main.init_schema", new_callable=AsyncMock) as init_schema:
        with pytest.raises(ValueError, match="disabled"):
            async with _lifespan(app):
                pytest.fail("Unsafe application must not start")
        init_schema.assert_not_awaited()
