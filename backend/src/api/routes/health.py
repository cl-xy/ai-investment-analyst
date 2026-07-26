"""
Health check endpoint with database connectivity verification.
"""

from fastapi import APIRouter

from ..db import fetchval
from ..schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready")
async def readiness():
    """
    Readiness probe. Verifies database connectivity.
    Returns 503 if the database is unreachable.
    """
    try:
        result = await fetchval("SELECT 1")
        db_ok = result == 1
    except Exception:
        db_ok = False

    if not db_ok:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "unreachable"},
        )

    return {"status": "ok", "database": "connected"}
