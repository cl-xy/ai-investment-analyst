"""
Operations dashboard API routes.

Provides extended health checks, metrics, traces, SLO monitoring,
and chaos injection endpoints for operational visibility.
"""

from __future__ import annotations

import hmac
import os
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from src.agent.circuit_breaker import llm_breaker
from src.agent.rate_limiter import llm_limiter
from src.cache.budget import get_budget_status
from src.db import fetchval
from src.logging_config import get_logger
from src.ops.chaos import chaos_config
from src.ops.collector import collector
from src.ops.trace_store import get_trace_by_id, get_trace_events, query_traces

log = get_logger("ops.routes")

router = APIRouter(prefix="/ops", tags=["ops"])

# Validation patterns
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_TRACE_ID_RE = re.compile(r"^[a-zA-Z0-9\-_]{1,64}$")
_VALID_STATUSES = {"success", "degraded", "failed"}


def _check_ops_auth(request: Request) -> bool:
    """
    Verify ops authentication. Uses the same DEMO_PASSWORD mechanism
    as the rest of the app for consistency.
    """
    demo_password = os.environ.get("DEMO_PASSWORD", "")
    if not demo_password:
        # No password configured, allow access (dev mode)
        return True
    provided = request.query_params.get("password") or request.headers.get("X-Demo-Password") or ""
    return hmac.compare_digest(provided.encode(), demo_password.encode())


@router.get("/health")
async def ops_health():
    """
    Extended health check with component statuses.

    Reports individual component health: database, LLM provider (circuit breaker
    and rate limiter state), and tool availability.
    """
    components: dict[str, Any] = {}
    overall = "healthy"

    # Database
    try:
        result = await fetchval("SELECT 1")
        components["database"] = {"status": "up", "connected": result == 1}
    except Exception as exc:
        log.error("health_db_check_failed", error=str(exc))
        components["database"] = {"status": "down", "error": "connection_failed"}
        overall = "unhealthy"

    # LLM provider (circuit breaker + rate limiter)
    cb_state = llm_breaker.state.value
    components["llm_provider"] = {
        "status": "up" if cb_state == "closed" else "degraded",
        "circuit_breaker": cb_state,
        "rate_limiter": {
            "tokens_available": round(llm_limiter._tokens, 2),
            "capacity": llm_limiter._capacity,
        },
    }
    if cb_state in ("open", "half_open"):
        overall = "degraded" if overall == "healthy" else overall

    # Budget status
    try:
        budget = await get_budget_status()
        components["budget"] = budget
        # Check if any provider is exhausted
        for provider, info in budget.items():
            if info.get("exhausted"):
                overall = "degraded" if overall == "healthy" else overall
    except Exception:
        components["budget"] = {"status": "unknown"}

    # Chaos injection state
    chaos_active = any(
        chaos_config.is_active(s)
        for s in ("llm_timeout", "mcp_failure", "rate_limit_exhausted", "slow_response")
    )
    components["chaos"] = {
        "any_active": chaos_active,
    }
    if chaos_active:
        overall = "degraded" if overall == "healthy" else overall

    return {
        "status": overall,
        "components": components,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics")
async def ops_metrics():
    """
    Current system metrics: request counts, error counts, latency percentiles,
    circuit breaker states, rate limit budget, cache hit rates, model call counts.
    """
    metrics_data = collector.get_metrics()

    # Enrich with live circuit breaker state
    metrics_data["circuit_breakers"] = {
        "llm_api": {
            "state": llm_breaker.state.value,
            "failure_count": len(llm_breaker._failures),
            "threshold": llm_breaker.failure_threshold,
        },
    }

    # Enrich with rate limiter state
    metrics_data["rate_limiter"] = {
        "tokens_available": round(llm_limiter._tokens, 2),
        "capacity": llm_limiter._capacity,
        "rate_per_second": llm_limiter._rate,
    }

    # Budget remaining
    try:
        budget = await get_budget_status()
        metrics_data["budget"] = budget
    except Exception:
        metrics_data["budget"] = {"status": "unavailable"}

    return metrics_data


@router.get("/traces")
async def ops_traces(
    ticker: str | None = Query(None, description="Filter by ticker symbol"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    status: str | None = Query(None, description="Filter by status: success/degraded/failed"),
):
    """
    Recent traces with timing breakdowns per stage.

    Returns the last N traces from both in-memory buffer and Postgres.
    Supports filtering by ticker and status.
    """
    # Validate ticker format
    if ticker:
        ticker = ticker.upper()
        if not _TICKER_RE.match(ticker):
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid ticker format. Must be 1-10 alphanumeric characters."},
            )

    # Validate status filter
    if status and status not in _VALID_STATUSES:
        return JSONResponse(
            status_code=400,
            content={
                "detail": f"Invalid status. Must be one of: {', '.join(sorted(_VALID_STATUSES))}"
            },
        )

    # First, try in-memory recent traces
    recent = collector.get_recent_traces(limit=limit + offset)

    # Also query persisted traces from Postgres
    try:
        persisted = await query_traces(
            ticker=ticker,
            status=status,
            limit=limit + offset,
            offset=0,
        )
    except Exception as exc:
        log.warning("trace_query_failed", error=str(exc))
        persisted = []

    # Merge: prefer persisted (has full data), supplement with in-memory
    # Deduplicate by correlation_id
    seen_ids = {t.get("correlation_id") for t in persisted if t.get("correlation_id")}
    for trace in recent:
        trace_cid = trace.get("correlation_id")
        if not trace_cid:
            continue
        if trace_cid not in seen_ids:
            # Apply filters if provided
            if ticker and (trace.get("ticker") or "").upper() != ticker:
                continue
            if status and trace.get("status") != status:
                continue
            persisted.append(trace)
            seen_ids.add(trace_cid)

    # Sort by time descending, apply offset and limit to merged result
    persisted.sort(key=lambda t: t.get("started_at") or t.get("created_at") or "", reverse=True)
    total = len(persisted)
    return {"traces": persisted[offset : offset + limit], "total": total}


@router.get("/traces/{trace_id}")
async def ops_trace_detail(trace_id: str):
    """Get a single trace with full event replay."""
    if not _TRACE_ID_RE.match(trace_id):
        return JSONResponse(status_code=400, content={"detail": "Invalid trace ID format"})
    trace = await get_trace_by_id(trace_id)
    if not trace:
        return JSONResponse(status_code=404, content={"detail": "Trace not found"})
    return trace


@router.get("/traces/{trace_id}/replay")
async def ops_trace_replay(trace_id: str):
    """Return ordered events for a given trace (replay support)."""
    if not _TRACE_ID_RE.match(trace_id):
        return JSONResponse(status_code=400, content={"detail": "Invalid trace ID format"})
    events = await get_trace_events(trace_id)
    if not events:
        return JSONResponse(
            status_code=404,
            content={"detail": "Trace not found or has no events"},
        )
    return {"trace_id": trace_id, "events": events, "event_count": len(events)}


@router.get("/slo")
async def ops_slo():
    """
    SLO targets vs actuals.

    Reports availability, latency, and error budget burn over a 7-day
    rolling window.
    """
    return collector.compute_slo()


@router.get("/costs")
async def ops_costs(
    days: int = Query(7, ge=1, le=90, description="Lookback period in days"),
):
    """Per-ticker cost breakdown for the ops dashboard."""
    from src.ops.cost_attribution import cost_attributor

    top_tickers = await cost_attributor.get_top_tickers(limit=10, days=days)
    daily = await cost_attributor.get_daily_costs(days=days)

    return {
        "top_tickers": top_tickers,
        "daily_costs": daily,
        "period_days": days,
    }


@router.get("/chaos")
async def ops_chaos_state():
    """Get current chaos injection state."""
    return {
        "scenarios": chaos_config.get_state(),
        "any_active": any(
            chaos_config.is_active(s)
            for s in ("llm_timeout", "mcp_failure", "rate_limit_exhausted", "slow_response")
        ),
    }


@router.post("/chaos")
async def ops_chaos_toggle(request: Request):
    """
    Toggle chaos scenarios. Requires auth.

    Body: {"scenario": "llm_timeout", "enabled": true}
    Or to reset all: {"reset": true}
    """
    if not _check_ops_auth(request):
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required for chaos operations"},
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid JSON body"},
        )

    # Reject non-object JSON bodies (arrays, strings, null, etc.)
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"detail": "Request body must be a JSON object"},
        )

    # Reset all scenarios
    if body.get("reset"):
        chaos_config.reset_all()
        return {"status": "ok", "message": "All chaos scenarios disabled"}

    scenario = body.get("scenario", "")
    enabled = body.get("enabled")

    # Validate enabled is a boolean
    if not isinstance(enabled, bool):
        return JSONResponse(
            status_code=400,
            content={"detail": "'enabled' must be a boolean (true or false)"},
        )

    valid_scenarios = ("llm_timeout", "mcp_failure", "rate_limit_exhausted", "slow_response")
    if scenario not in valid_scenarios:
        return JSONResponse(
            status_code=400,
            content={
                "detail": f"Invalid scenario. Must be one of: {', '.join(valid_scenarios)}",
            },
        )

    try:
        success = chaos_config.toggle(scenario, enabled)
    except Exception as exc:
        log.error("chaos_toggle_failed", scenario=scenario, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "Failed to toggle scenario"},
        )

    if not success:
        return JSONResponse(
            status_code=500,
            content={"detail": "Failed to toggle scenario"},
        )

    return {
        "status": "ok",
        "scenario": scenario,
        "enabled": enabled,
        "state": chaos_config.get_state(),
    }
