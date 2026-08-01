"""
Health check endpoints: liveness and readiness probes.

GET /api/health       -> liveness (always 200 if the app is running)
GET /api/health/ready -> readiness (checks DB, reports provider status)
"""

import asyncio
import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.agent.circuit_breaker import llm_breaker
from src.cache.budget import DAILY_LIMITS, get_budget_status
from src.db import fetchval

logger = logging.getLogger(__name__)

router = APIRouter()

# Track when the app started for uptime calculation
_start_time = time.monotonic()

# Timeouts for dependency checks (seconds)
_DB_TIMEOUT = 3.0
_BUDGET_TIMEOUT = 2.0


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

    # 1. Database check (with timeout to prevent hung probes)
    db_start = time.monotonic()
    try:
        result = await asyncio.wait_for(fetchval("SELECT 1"), timeout=_DB_TIMEOUT)
        db_ok = result == 1
        db_latency = round((time.monotonic() - db_start) * 1000, 1)
        if db_ok:
            checks["database"] = {"status": "up", "latency_ms": db_latency}
        else:
            checks["database"] = {"status": "down", "latency_ms": db_latency}
            status = "unhealthy"
    except asyncio.TimeoutError:
        db_ok = False
        db_latency = round((time.monotonic() - db_start) * 1000, 1)
        checks["database"] = {"status": "timeout", "latency_ms": db_latency}
        status = "unhealthy"
        logger.warning("Health check: database timed out after %.1fms", db_latency)
    except Exception as exc:
        db_ok = False
        db_latency = round((time.monotonic() - db_start) * 1000, 1)
        checks["database"] = {"status": "down", "latency_ms": db_latency}
        status = "unhealthy"
        logger.warning("Health check: database error: %s", type(exc).__name__)

    # 2. LLM budget check (with timeout)
    if db_ok:
        try:
            budget_status = await asyncio.wait_for(get_budget_status(), timeout=_BUDGET_TIMEOUT)
            llm_budget = budget_status.get("openrouter", {})
            remaining = llm_budget.get("remaining", 0)
            limit = DAILY_LIMITS.get("openrouter", 1400)
            # "low" if less than 10% remaining
            budget_ok = remaining > (limit * 0.1)
            checks["llm_budget"] = {
                "status": "ok" if budget_ok else "low",
                "remaining_today": remaining,
            }
            if not budget_ok:
                status = "degraded" if status == "healthy" else status
        except asyncio.TimeoutError:
            checks["llm_budget"] = {"status": "unknown"}
            status = "degraded" if status == "healthy" else status
            logger.warning("Health check: budget status timed out")
        except Exception as exc:
            checks["llm_budget"] = {"status": "unknown"}
            status = "degraded" if status == "healthy" else status
            logger.warning("Health check: budget status error: %s", type(exc).__name__)

    # 3. Circuit breaker state
    try:
        cb_state = llm_breaker.state.value
        checks["circuit_breaker"] = {
            "status": cb_state,
            "provider": "openrouter",
        }
        if cb_state in ("open", "half_open"):
            status = "degraded" if status == "healthy" else status
    except Exception as exc:
        checks["circuit_breaker"] = {"status": "unknown", "provider": "openrouter"}
        logger.warning("Health check: circuit breaker error: %s", type(exc).__name__)

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
