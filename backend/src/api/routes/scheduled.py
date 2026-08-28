import asyncio
import json
import logging
from datetime import date, datetime, timezone
from secrets import compare_digest
from time import perf_counter

from fastapi import APIRouter, Header, HTTPException, Request

from src.agent.concurrency import acquire_analysis_slot, release_analysis_slot
from src.alerts.pipeline import evaluate_all_monitored
from src.config import settings
from src.db import fetchrow
from src.mcp_servers.portfolio_server import fetch_all_positions

from ..schemas import AlertEvaluationResponse, ScheduledRefreshResponse
from .analyze import analyze_tickers

router = APIRouter()
logger = logging.getLogger(__name__)

_RUN_LOCK = asyncio.Lock()
_LAST_REFRESH_STARTED_AT: datetime | None = None

_EARNINGS_RUN_LOCK = asyncio.Lock()

_ALERT_EVAL_LOCK = asyncio.Lock()


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
        # Re-check lock window inside the lock to close TOCTOU race:
        # two requests can both pass the unlocked check above, but only
        # one should proceed once the lock is acquired.
        if _LAST_REFRESH_STARTED_AT is not None:
            elapsed = (datetime.now(timezone.utc) - _LAST_REFRESH_STARTED_AT).total_seconds()
            if elapsed < settings.scheduler_refresh_lock_seconds:
                return ScheduledRefreshResponse(
                    status="skipped",
                    message="Refresh skipped due to lock window",
                    tickers=[],
                    created_at=datetime.now(timezone.utc),
                    duration_ms=int((perf_counter() - started) * 1000),
                )

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

        # Only set the lock-window timestamp after slot is acquired, so failed
        # slot acquisitions don't block future retries during the window.
        _LAST_REFRESH_STARTED_AT = datetime.now(timezone.utc)

        # Hard timeout: same rationale as earnings refresh. Without this, a slow
        # LLM run holds _RUN_LOCK + analysis slot indefinitely.
        _PORTFOLIO_TIMEOUT = 300  # seconds — generous for multi-ticker portfolio
        try:
            logger.info("scheduled_refresh_started tickers=%s", tickers)
            mcp_tools = request.app.state.mcp_tools
            analysis = await asyncio.wait_for(
                analyze_tickers(tickers, mcp_tools, force_refresh=True),
                timeout=_PORTFOLIO_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error(
                "scheduled_refresh_timeout tickers=%s timeout=%ds",
                tickers,
                _PORTFOLIO_TIMEOUT,
            )
            return ScheduledRefreshResponse(
                status="failed",
                message=f"Portfolio refresh timed out after {_PORTFOLIO_TIMEOUT}s",
                tickers=tickers,
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )
        except Exception:
            logger.exception(
                "scheduled_refresh_error tickers=%s",
                tickers,
            )
            return ScheduledRefreshResponse(
                status="failed",
                message="Portfolio refresh failed unexpectedly",
                tickers=tickers,
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )
        finally:
            release_analysis_slot()

        logger.info(
            "scheduled_refresh_finished tickers=%s analysis_id=%s duration_ms=%s",
            tickers,
            analysis.id,
            int((perf_counter() - started) * 1000),
        )

        # Best-effort hook: piggyback a full alert-evaluation pass on a
        # successful portfolio refresh. Note this deliberately does NOT
        # re-check the tickers just refreshed above — force_refresh=True
        # means their new analysis *is* the fresh baseline, so drift against
        # itself would always be zero. Instead this catches drift on any
        # other monitored ticker (e.g. watchlist-only subscriptions) using
        # already-warm probe caches. Fire-and-forget: must not extend this
        # endpoint's response latency or be bound by its timeout.
        asyncio.create_task(_evaluate_alerts_best_effort())

        return ScheduledRefreshResponse(
            status="success",
            message="Portfolio analysis refreshed",
            tickers=tickers,
            analysis_id=analysis.id,
            created_at=analysis.created_at,
            duration_ms=int((perf_counter() - started) * 1000),
        )


async def _evaluate_alerts_best_effort() -> None:
    """Run a full monitored-universe drift evaluation without holding up the
    refresh-portfolio response. Swallows all exceptions — this is
    observability/notification, not part of the refresh contract."""
    from src.alerts.pipeline import evaluate_all_monitored

    try:
        await evaluate_all_monitored()
    except Exception:
        logger.warning("post_refresh_alert_evaluation_failed", exc_info=True)


async def _ticker_due_for_earnings_refresh(ticker: str) -> bool:
    """A ticker is due if its last known earnings date has already passed
    without a subsequent analysis (a fresh analysis would carry a future
    next_earnings_date instead)."""
    row = await fetchrow(
        """
        SELECT ta.earnings
        FROM ticker_analyses ta
        JOIN analyses a ON ta.analysis_id = a.id
        WHERE ta.ticker = $1
        ORDER BY a.created_at DESC
        LIMIT 1
        """,
        ticker,
    )
    if not row:
        return False

    earnings = row["earnings"]
    if isinstance(earnings, str):
        try:
            earnings = json.loads(earnings)
        except (json.JSONDecodeError, ValueError):
            return False
    if not isinstance(earnings, dict):
        return False

    next_date_str = earnings.get("next_earnings_date")
    if not next_date_str:
        return False
    try:
        next_date = date.fromisoformat(next_date_str)
    except ValueError:
        return False

    return next_date < datetime.now(timezone.utc).date()


@router.post("/scheduled/refresh-earnings", response_model=ScheduledRefreshResponse)
async def refresh_earnings_tickers(
    request: Request,
    x_scheduler_token: str | None = Header(default=None),
) -> ScheduledRefreshResponse:
    """
    Lightweight, frequent check: force-refresh only portfolio tickers whose
    last known earnings date has passed since their last analysis.

    Deliberately decoupled from the once-daily refresh-portfolio job above —
    the whole point is faster reaction than a fixed daily cadence, so this is
    meant to be polled more often (e.g. every few hours) by its own workflow.
    """
    now = datetime.now(timezone.utc)
    started = perf_counter()

    expected_token = settings.scheduler_secret_token
    if not expected_token:
        raise HTTPException(status_code=503, detail="Scheduler token is not configured")
    if not x_scheduler_token or not compare_digest(x_scheduler_token, expected_token):
        raise HTTPException(status_code=401, detail="Unauthorized scheduler request")

    if _EARNINGS_RUN_LOCK.locked():
        return ScheduledRefreshResponse(
            status="skipped",
            message="Earnings refresh check is already running",
            tickers=[],
            created_at=now,
            duration_ms=int((perf_counter() - started) * 1000),
        )

    async with _EARNINGS_RUN_LOCK:
        positions = await fetch_all_positions()
        all_tickers = _get_unique_portfolio_tickers(positions)

        if not all_tickers:
            return ScheduledRefreshResponse(
                status="skipped",
                message="Portfolio is empty; no tickers to check",
                tickers=[],
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )

        due_flags = await asyncio.gather(
            *[_ticker_due_for_earnings_refresh(t) for t in all_tickers],
            return_exceptions=True,
        )
        due_tickers = [t for t, result in zip(all_tickers, due_flags) if result is True]

        if not due_tickers:
            logger.info("earnings_refresh_check_none_due tickers_checked=%s", all_tickers)
            return ScheduledRefreshResponse(
                status="skipped",
                message="No tickers have a passed earnings date since their last analysis",
                tickers=[],
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )

        slot_acquired = await acquire_analysis_slot()
        if not slot_acquired:
            logger.warning("earnings_refresh_skipped_no_slot")
            return ScheduledRefreshResponse(
                status="skipped",
                message="Server at capacity; earnings refresh deferred",
                tickers=due_tickers,
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )

        # Hard timeout: must complete before GitHub Actions curl --max-time (120s)
        # and before Fly.io proxy drops the connection. Without this, a slow LLM
        # run orphans the coroutine (Uvicorn does NOT cancel on client disconnect)
        # and holds the analysis slot + lock indefinitely.
        _EARNINGS_TIMEOUT = 100  # seconds — below GHA's 120s curl limit
        try:
            logger.info("earnings_refresh_started tickers=%s", due_tickers)
            mcp_tools = request.app.state.mcp_tools
            analysis = await asyncio.wait_for(
                analyze_tickers(due_tickers, mcp_tools, force_refresh=True),
                timeout=_EARNINGS_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error(
                "earnings_refresh_timeout tickers=%s timeout=%ds",
                due_tickers,
                _EARNINGS_TIMEOUT,
            )
            return ScheduledRefreshResponse(
                status="failed",
                message=f"Earnings refresh timed out after {_EARNINGS_TIMEOUT}s",
                tickers=due_tickers,
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )
        except Exception:
            logger.exception(
                "earnings_refresh_error tickers=%s",
                due_tickers,
            )
            return ScheduledRefreshResponse(
                status="failed",
                message="Earnings refresh failed unexpectedly",
                tickers=due_tickers,
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )
        finally:
            release_analysis_slot()

        logger.info(
            "earnings_refresh_finished tickers=%s analysis_id=%s duration_ms=%s",
            due_tickers,
            analysis.id,
            int((perf_counter() - started) * 1000),
        )
        return ScheduledRefreshResponse(
            status="success",
            message="Post-earnings analysis refreshed",
            tickers=due_tickers,
            analysis_id=analysis.id,
            created_at=analysis.created_at,
            duration_ms=int((perf_counter() - started) * 1000),
        )


@router.post("/scheduled/evaluate-alerts", response_model=AlertEvaluationResponse)
async def evaluate_alerts(
    request: Request,
    x_scheduler_token: str | None = Header(default=None),
) -> AlertEvaluationResponse:
    """
    Reasoning-Aware Signal Alerts: evaluate every monitored ticker (portfolio
    positions + opted-in watchlist subscriptions) for drift since its last
    analysis, and dispatch Telegram alerts for anything material.

    Deliberately decoupled from refresh-portfolio/refresh-earnings — this
    doesn't run a full re-analysis, just the lightweight probe + heuristic
    scorer (+ conditional LLM judge) pipeline, so it's safe to run more
    frequently (e.g. every 2h during market hours).
    """
    now = datetime.now(timezone.utc)
    started = perf_counter()

    expected_token = settings.scheduler_secret_token
    if not expected_token:
        raise HTTPException(status_code=503, detail="Scheduler token is not configured")
    if not x_scheduler_token or not compare_digest(x_scheduler_token, expected_token):
        raise HTTPException(status_code=401, detail="Unauthorized scheduler request")

    if _ALERT_EVAL_LOCK.locked():
        return AlertEvaluationResponse(
            status="skipped",
            message="Alert evaluation is already running",
            created_at=now,
            duration_ms=int((perf_counter() - started) * 1000),
        )

    async with _ALERT_EVAL_LOCK:
        slot_acquired = await acquire_analysis_slot()
        if not slot_acquired:
            logger.warning("alert_evaluation_skipped_no_slot")
            return AlertEvaluationResponse(
                status="skipped",
                message="Server at capacity; alert evaluation deferred",
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )

        # Hard timeout: below GitHub Actions' curl --max-time (120s) and Fly's
        # proxy idle limit. Each ticker's evaluation is itself bounded (probe
        # timeouts + a single fast LLM call), so this should rarely trip, but
        # without it a stuck probe could hold the lock + slot indefinitely.
        _ALERT_EVAL_TIMEOUT = 100  # seconds
        try:
            logger.info("alert_evaluation_started")
            summary = await asyncio.wait_for(
                evaluate_all_monitored(), timeout=_ALERT_EVAL_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error("alert_evaluation_timeout timeout=%ds", _ALERT_EVAL_TIMEOUT)
            return AlertEvaluationResponse(
                status="failed",
                message=f"Alert evaluation timed out after {_ALERT_EVAL_TIMEOUT}s",
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )
        except Exception:
            logger.exception("alert_evaluation_error")
            return AlertEvaluationResponse(
                status="failed",
                message="Alert evaluation failed unexpectedly",
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )
        finally:
            release_analysis_slot()

        logger.info(
            "alert_evaluation_finished tickers=%d alerts_fired=%d duration_ms=%s",
            summary.tickers_evaluated,
            summary.alerts_fired,
            int((perf_counter() - started) * 1000),
        )
        return AlertEvaluationResponse(
            status="success",
            message=f"Evaluated {summary.tickers_evaluated} ticker(s), fired {summary.alerts_fired} alert(s)",
            tickers_evaluated=summary.tickers_evaluated,
            alerts_fired=summary.alerts_fired,
            llm_calls_used=summary.llm_calls_used,
            heuristic_only_count=summary.heuristic_only_count,
            created_at=datetime.now(timezone.utc),
            duration_ms=int((perf_counter() - started) * 1000),
        )
