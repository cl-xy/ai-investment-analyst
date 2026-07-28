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

    result = await execute("DELETE FROM ticker_analyses WHERE signal = 'insufficient_data'")
    deleted = int(result.split()[-1]) if result else 0
    return {"status": "ok", "deleted": deleted}


@router.delete("/purge-empty-cache")
async def purge_empty_cache(authorization: str | None = Header(default=None)):
    """Delete cache entries with empty payloads that poison the data pipeline."""
    _verify_token(authorization)

    from src.db import execute

    result = await execute(
        """DELETE FROM cache WHERE
           data::text IN ('{}', '[]', '""', 'null', '')
           OR data IS NULL"""
    )
    deleted = int(result.split()[-1]) if result else 0
    return {"status": "ok", "deleted": deleted}


@router.get("/cache-inspect/{ticker}")
async def inspect_cache(ticker: str, authorization: str | None = Header(default=None)):
    """Inspect all cache entries for a ticker to diagnose data pipeline issues."""
    _verify_token(authorization)

    from src.db import fetch

    rows = await fetch(
        "SELECT key, data, source_id, provider, fetched_at, stale_at, expires_at FROM cache WHERE key LIKE $1",
        f"%:{ticker.upper()}",
    )
    entries = []
    for row in rows:
        data = row["data"]
        # Summarize the data (first 200 chars or key count)
        if isinstance(data, dict):
            summary = {
                k: ("..." if isinstance(v, (dict, list)) else v) for k, v in list(data.items())[:10]
            }
        elif isinstance(data, list):
            summary = f"[list of {len(data)} items]"
        else:
            summary = str(data)[:200]
        entries.append(
            {
                "key": row["key"],
                "provider": row["provider"],
                "data_summary": summary,
                "data_is_empty": data in ({}, [], "", None),
                "fetched_at": str(row["fetched_at"]),
                "stale_at": str(row["stale_at"]),
                "expires_at": str(row["expires_at"]),
            }
        )
    return {"ticker": ticker.upper(), "entries": entries, "count": len(entries)}


@router.get("/tool-test/{ticker}")
async def test_tool_live(ticker: str, authorization: str | None = Header(default=None)):
    """Call get_quote directly (bypassing cache) to diagnose tool failures."""
    _verify_token(authorization)

    import asyncio
    import time

    from src.mcp_servers.market_server.sources.yfinance_client import get_quote

    start = time.monotonic()
    try:
        result = await asyncio.to_thread(get_quote, ticker.upper())
        duration_ms = int((time.monotonic() - start) * 1000)
        return {"status": "ok", "duration_ms": duration_ms, "data": result}
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "error",
            "duration_ms": duration_ms,
            "error": str(e),
            "type": type(e).__name__,
        }


@router.get("/health/detailed")
async def detailed_health():
    """Extended health check with system info (public, no auth)."""
    return {
        "status": "healthy",
        "version": "0.2.0",
        "demo_tickers": DEMO_TICKERS,
    }
