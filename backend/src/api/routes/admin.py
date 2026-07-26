"""
Admin endpoints for cache management and system status.
Protected by scheduler secret token.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException, Request

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
    if provided != token:
        raise HTTPException(status_code=403, detail="Invalid token")


@router.post("/warm-cache")
async def warm_cache(request: Request, authorization: str | None = Header(default=None)):
    """
    Pre-warm cache for demo tickers.
    Called by GitHub Actions nightly cron.
    """
    _verify_token(authorization)

    mcp_tools = request.app.state.mcp_tools
    warmed = []
    failed = []

    for ticker in DEMO_TICKERS:
        try:
            # Call each data-fetching tool to populate cache
            tools_to_warm = ["get_quote", "get_fundamentals", "get_technical_indicators", "get_ticker_news"]
            for tool_name in tools_to_warm:
                tool = mcp_tools.get(tool_name)
                if tool:
                    try:
                        await tool.ainvoke({"ticker": ticker})
                    except Exception:
                        pass  # Individual tool failure is non-critical
            warmed.append(ticker)
        except Exception as exc:
            failed.append({"ticker": ticker, "error": str(exc)})

    return {
        "status": "ok",
        "warmed": warmed,
        "failed": failed,
        "message": f"Cache warmed for {len(warmed)}/{len(DEMO_TICKERS)} tickers",
    }


@router.get("/budget")
async def budget_status(authorization: str | None = Header(default=None)):
    """Return current API budget usage for all tracked providers."""
    _verify_token(authorization)
    status = await get_budget_status()
    return {"status": "ok", "budgets": status}


@router.get("/health/detailed")
async def detailed_health():
    """Extended health check with system info (public, no auth)."""
    return {
        "status": "healthy",
        "version": "0.2.0",
        "demo_tickers": DEMO_TICKERS,
    }
