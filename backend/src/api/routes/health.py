"""
Health check endpoints: liveness and readiness probes.

GET /api/health       -> liveness (always 200 if the app is running)
GET /api/health/ready -> readiness (checks DB, reports provider status)
"""

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.cache.budget import DAILY_LIMITS, get_budget_status
from src.db import fetchval

router = APIRouter()

# Track when the app started for uptime calculation
_start_time = time.monotonic()


@router.get("/health")
async def liveness():
    """Liveness probe. Returns 200 if the process is alive."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    """
    Readiness probe. Checks actual dependencies and reports degraded state.

    Status semantics:
    - healthy: all systems operational
    - degraded: circuit breaker open or budget low, but cached results available
    - unhealthy: database unreachable
    """
    checks: dict = {}
    status = "healthy"

    # 1. Database check
    db_start = time.monotonic()
    try:
        result = await fetchval("SELECT 1")
        db_ok = result == 1
        db_latency = round((time.monotonic() - db_start) * 1000, 1)
        checks["database"] = {"status": "up", "latency_ms": db_latency}
    except Exception:
        db_ok = False
        checks["database"] = {"status": "down"}
        status = "unhealthy"

    # 2. LLM budget check
    if db_ok:
        try:
            budget_status = await get_budget_status()
            llm_budget = budget_status.get("openrouter", budget_status.get("groq", {}))
            remaining = llm_budget.get("remaining", 0)
            limit = DAILY_LIMITS.get("openrouter", DAILY_LIMITS.get("groq", 1400))
            # "low" if less than 10% remaining
            budget_ok = remaining > (limit * 0.1)
            checks["llm_budget"] = {
                "status": "ok" if budget_ok else "low",
                "remaining_today": remaining,
            }
            if not budget_ok:
                status = "degraded" if status == "healthy" else status
        except Exception:
            checks["llm_budget"] = {"status": "unknown"}

    # 3. Circuit breaker state
    try:
        from src.agent.circuit_breaker import llm_breaker

        cb_state = llm_breaker.state.value
        checks["circuit_breaker"] = {
            "status": cb_state,
            "provider": "openrouter",
        }
        if cb_state in ("open", "half_open"):
            status = "degraded" if status == "healthy" else status
    except Exception:
        checks["circuit_breaker"] = {"status": "unknown", "provider": "openrouter"}

    uptime = round(time.monotonic() - _start_time, 1)

    body = {
        "status": status,
        "checks": checks,
        "version": "0.2.0",
        "uptime_seconds": uptime,
    }

    if status == "unhealthy":
        return JSONResponse(status_code=503, content=body)

    return body
