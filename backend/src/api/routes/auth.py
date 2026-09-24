"""
Login endpoint for the frontend's username/password gate.

Not a real multi-user auth system: validates against a single admin
username/password (ADMIN_USERNAME / ADMIN_PASSWORD env vars, with
defaults so the app is usable out of the box) and returns a signed,
expiring session token on success.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.middleware.auth import ADMIN_PASSWORD, ADMIN_USERNAME, create_session_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    username_ok = hmac.compare_digest(body.username.encode(), ADMIN_USERNAME.encode())
    password_ok = hmac.compare_digest(body.password.encode(), ADMIN_PASSWORD.encode())

    if not (username_ok and password_ok):
        logger.warning("Login failed for username %r", body.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return LoginResponse(token=create_session_token(body.username))
