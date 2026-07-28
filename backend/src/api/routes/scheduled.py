import asyncio
import logging
from datetime import datetime, timezone
from secrets import compare_digest
from time import perf_counter

from fastapi import APIRouter, Header, HTTPException, Request

from src.agent.concurrency import acquire_analysis_slot, release_analysis_slot
from src.config import settings
from src.mcp_servers.portfolio_server import fetch_all_positions

from ..schemas import ScheduledRefreshResponse
from .analyze import analyze_tickers

router = APIRouter()
logger = logging.getLogger(__name__)

_RUN_LOCK = asyncio.Lock()
_LAST_REFRESH_STARTED_AT: datetime | None = None


def _get_unique_portfolio_tickers(positions: list[dict]) -> list[str]:
    seen: set[str] = set()
    tickers: list[str] = []
    for position in positions:
        ticker = str(position.get("ticker", "")).strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers


@router.post("/scheduled/refresh-portfolio", response_model=ScheduledRefreshResponse)
async def refresh_portfolio_analyses(
    request: Request,
    x_scheduler_token: str | None = Header(default=None),
) -> ScheduledRefreshResponse:
    now = datetime.now(timezone.utc)
    started = perf_counter()

    expected_token = settings.scheduler_secret_token
    if not expected_token:
        raise HTTPException(status_code=503, detail="Scheduler token is not configured")
    if not x_scheduler_token or not compare_digest(x_scheduler_token, expected_token):
        raise HTTPException(status_code=401, detail="Unauthorized scheduler request")

    global _LAST_REFRESH_STARTED_AT
    if _RUN_LOCK.locked():
        return ScheduledRefreshResponse(
            status="skipped",
            message="Refresh is already running",
            tickers=[],
            created_at=now,
            duration_ms=int((perf_counter() - started) * 1000),
        )

    if _LAST_REFRESH_STARTED_AT is not None:
        elapsed = (now - _LAST_REFRESH_STARTED_AT).total_seconds()
        if elapsed < settings.scheduler_refresh_lock_seconds:
            return ScheduledRefreshResponse(
                status="skipped",
                message="Refresh skipped due to lock window",
                tickers=[],
                created_at=now,
                duration_ms=int((perf_counter() - started) * 1000),
            )

    async with _RUN_LOCK:
        _LAST_REFRESH_STARTED_AT = datetime.now(timezone.utc)
        positions = await fetch_all_positions()
        tickers = _get_unique_portfolio_tickers(positions)

        if not tickers:
            logger.info("scheduled_refresh_skipped_empty_portfolio")
            return ScheduledRefreshResponse(
                status="skipped",
                message="Portfolio is empty; no tickers to refresh",
                tickers=[],
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )

        # Acquire concurrency slot to avoid starving streaming analyses
        slot_acquired = await acquire_analysis_slot()
        if not slot_acquired:
            logger.warning("scheduled_refresh_skipped_no_slot")
            return ScheduledRefreshResponse(
                status="skipped",
                message="Server at capacity; scheduled refresh deferred",
                tickers=tickers,
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )

        try:
            logger.info("scheduled_refresh_started tickers=%s", tickers)
            mcp_tools = request.app.state.mcp_tools
            analysis = await analyze_tickers(tickers, mcp_tools, force_refresh=True)
        finally:
            release_analysis_slot()

        logger.info(
            "scheduled_refresh_finished tickers=%s analysis_id=%s duration_ms=%s",
            tickers,
            analysis.id,
            int((perf_counter() - started) * 1000),
        )
        return ScheduledRefreshResponse(
            status="success",
            message="Portfolio analysis refreshed",
            tickers=tickers,
            analysis_id=analysis.id,
            created_at=analysis.created_at,
            duration_ms=int((perf_counter() - started) * 1000),
        )
