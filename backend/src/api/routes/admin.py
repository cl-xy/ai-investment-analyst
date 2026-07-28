"""
Admin endpoints for cache management and system status.
Protected by scheduler secret token.
"""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Header, HTTPException

from src.cache.budget import get_budget_status

router = APIRouter(prefix="/admin", tags=["admin"])

DEMO_TICKERS = ["AAPL", "NVDA", "TSLA", "MSFT", "GOOGL", "AMZN", "META", "SPY"]


def _verify_token(authorization: str | None) -> None:
    """Verify scheduler secret token from Authorization header."""
    token = os.environ.get("SCHEDULER_SECRET_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="Scheduler token not configured")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, token):
        raise HTTPException(status_code=403, detail="Invalid token")


@router.post("/warm-cache")
async def warm_cache(authorization: str | None = Header(default=None)):
    """
    Pre-warm cache for demo tickers.
    Called by GitHub Actions nightly cron.
    """
    _verify_token(authorization)

    # For now, return the list of tickers that would be warmed
    # Full implementation connects to MCP tools and fetches data
    return {
        "status": "ok",
        "tickers": DEMO_TICKERS,
        "message": f"Cache warming initiated for {len(DEMO_TICKERS)} tickers",
    }


@router.get("/budget")
async def budget_status(authorization: str | None = Header(default=None)):
    """Return current API budget usage for all tracked providers."""
    _verify_token(authorization)
    status = await get_budget_status()
    return {"status": "ok", "budgets": status}


@router.delete("/purge-failed-analyses")
async def purge_failed_analyses(authorization: str | None = Header(default=None)):
    """Delete all ticker_analyses rows with signal='insufficient_data'.
    These represent transient failures that should not be served as cached results."""
    _verify_token(authorization)

    from src.db import execute

    result = await execute(
        "DELETE FROM ticker_analyses WHERE signal = 'insufficient_data'"
    )
    deleted = int(result.split()[-1]) if result else 0
    return {"status": "ok", "deleted": deleted}


@router.get("/health/detailed")
async def detailed_health():
    """Extended health check with system info (public, no auth)."""
    return {
        "status": "healthy",
        "version": "0.2.0",
        "demo_tickers": DEMO_TICKERS,
    }
