import asyncio
import json
import logging
from datetime import date, datetime, timezone
from secrets import compare_digest
from time import perf_counter
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request

from src.agent.concurrency import acquire_analysis_slot, release_analysis_slot
from src.alerts.pipeline import evaluate_all_monitored
from src.config import settings
from src.db import execute, fetchrow
from src.mcp_servers.portfolio_server import fetch_all_positions

from ..schemas import AlertEvaluationResponse, DigestResponse, ScheduledRefreshResponse
from .analyze import analyze_tickers

router = APIRouter()
logger = logging.getLogger(__name__)

_RUN_LOCK = asyncio.Lock()
_LAST_REFRESH_STARTED_AT: datetime | None = None

_EARNINGS_RUN_LOCK = asyncio.Lock()

_ALERT_EVAL_LOCK = asyncio.Lock()

_DIGEST_LOCK = asyncio.Lock()

# Eastern Time is the reference clock for "one digest per day" because the
# digest is anchored to market close (16:30 ET), not midnight UTC — using
# UTC dates would let a run just after UTC midnight but before ET midnight
# collide with, or miss, the intended trading day.
_ET_ZONE = ZoneInfo("America/New_York")


def _current_et_date() -> date:
    return datetime.now(_ET_ZONE).date()


async def _digest_already_sent_today() -> date | None:
    """Return today's ET date if a successful digest was already recorded
    for it, else None. Extracted from the route handler to keep it under
    the route-body line limit enforced by TestRoutesAreThin."""
    send_date = _current_et_date()
    row = await fetchrow(
        "SELECT id FROM digest_sends WHERE send_date = $1 AND status = 'success'",
        send_date,
    )
    return send_date if row is not None else None


async def _record_digest_sent(send_date: date, sent_to: int, tickers_included: int) -> None:
    """Persist today's send under its ET date so a later duplicate/jittered
    cron tick is caught by _digest_already_sent_today(). ON CONFLICT DO
    NOTHING guards the narrow race where two ticks both pass that check
    before either reaches this insert — the UNIQUE(send_date) constraint on
    the table is the real guard, this just avoids an unhandled exception on
    the loser of that race."""
    await execute(
        """INSERT INTO digest_sends (send_date, status, sent_to, tickers_included)
           VALUES ($1, 'success', $2, $3)
           ON CONFLICT (send_date) DO NOTHING""",
        send_date,
        sent_to,
        tickers_included,
    )


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
            summary = await asyncio.wait_for(evaluate_all_monitored(), timeout=_ALERT_EVAL_TIMEOUT)
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


async def _build_and_send_digest(started: float) -> DigestResponse:
    """Build the digest message from cached data and dispatch it to every
    active Telegram chat. Extracted to module level (out of send_digest's
    body) to keep the route handler within TestRoutesAreThin's line limit —
    this function does the actual work; the route just wires auth,
    idempotency, locking, and the timeout around it."""
    from src.alerts.composer import get_recent_alerts
    from src.alerts.last_analysis import get_last_analysis
    from src.alerts.pipeline import get_monitored_tickers
    from src.alerts.telegram import (
        DigestAlertEntry,
        DigestTickerEntry,
        _call_telegram,
        build_digest_message,
        get_active_chat_ids,
    )

    tickers = await get_monitored_tickers()

    ticker_entries: list[DigestTickerEntry] = []
    for ticker in tickers:
        try:
            snapshot = await get_last_analysis(ticker)
        except Exception:
            logger.warning("digest_ticker_lookup_failed ticker=%s", ticker, exc_info=True)
            continue
        if snapshot is not None:
            ticker_entries.append(
                DigestTickerEntry(
                    ticker=snapshot.ticker,
                    signal=snapshot.signal,
                    confidence=snapshot.confidence,
                    sentiment_score=snapshot.sentiment_score,
                    thesis=snapshot.thesis,
                    risk_flags=tuple(snapshot.risk_flags),
                )
            )

    try:
        recent_alert_rows = await get_recent_alerts(since_hours=24)
    except Exception:
        logger.warning("digest_recent_alerts_lookup_failed", exc_info=True)
        recent_alert_rows = []

    alert_entries = [
        DigestAlertEntry(
            ticker=row["ticker"],
            severity=row["severity"],
            alert_type=row["alert_type"],
            created_at=row["created_at"],
        )
        for row in recent_alert_rows
    ]

    message = build_digest_message(ticker_entries, alert_entries, settings.frontend_url)
    if message is None:
        logger.info("digest_skipped_no_monitored_tickers")
        return DigestResponse(
            status="skipped",
            message="No monitored tickers to include in digest",
            tickers_included=0,
            recent_alerts_included=len(alert_entries),
            created_at=datetime.now(timezone.utc),
            duration_ms=int((perf_counter() - started) * 1000),
        )

    chat_ids = await get_active_chat_ids()
    sent = 0
    for chat_id in chat_ids:
        result = await _call_telegram(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
        )
        if result is not None and result.get("ok"):
            sent += 1

    await _record_digest_sent(
        _current_et_date(), sent_to=sent, tickers_included=len(ticker_entries)
    )

    return DigestResponse(
        status="success",
        message=f"Digest sent to {sent}/{len(chat_ids)} chat(s)",
        tickers_included=len(ticker_entries),
        recent_alerts_included=len(alert_entries),
        sent_to=sent,
        created_at=datetime.now(timezone.utc),
        duration_ms=int((perf_counter() - started) * 1000),
    )


@router.post("/scheduled/send-digest", response_model=DigestResponse)
async def send_digest(
    request: Request,
    x_scheduler_token: str | None = Header(default=None),
) -> DigestResponse:
    """
    Daily digest: push a summary of every monitored ticker's latest cached
    signal, plus any alerts fired in the last 24h, to every registered
    Telegram chat.

    Strictly read-only against already-cached data (ticker_analyses, alerts)
    — this never triggers a fresh analysis or an LLM call, so it's safe to
    run on a simple once-daily cron regardless of budget state.
    """
    now = datetime.now(timezone.utc)
    started = perf_counter()

    expected_token = settings.scheduler_secret_token
    if not expected_token:
        raise HTTPException(status_code=503, detail="Scheduler token is not configured")
    if not x_scheduler_token or not compare_digest(x_scheduler_token, expected_token):
        raise HTTPException(status_code=401, detail="Unauthorized scheduler request")

    if _DIGEST_LOCK.locked():
        return DigestResponse(
            status="skipped",
            message="Digest send is already running",
            created_at=now,
            duration_ms=int((perf_counter() - started) * 1000),
        )

    # Idempotency guard: at most one successful digest per ET calendar day.
    # The scheduling workflow now runs on a tolerant multi-hour window
    # (instead of a single exact-minute match) so a delayed or jittered cron
    # tick still fires — this check is what makes repeated/late ticks safe
    # instead of causing duplicate sends. DB-backed (not in-process) so it
    # holds across restarts and across multiple Fly.io machines.
    already_sent_date = await _digest_already_sent_today()
    if already_sent_date is not None:
        return DigestResponse(
            status="skipped",
            message=f"Digest already sent today ({already_sent_date.isoformat()} ET)",
            created_at=now,
            duration_ms=int((perf_counter() - started) * 1000),
        )

    async with _DIGEST_LOCK:
        # Hard timeout: below GitHub Actions' curl --max-time (120s). This
        # endpoint only reads cached rows and sends Telegram messages, so it
        # should be fast, but a stuck DB connection or slow Telegram API call
        # shouldn't be able to hold the lock indefinitely.
        _DIGEST_TIMEOUT = 60  # seconds

        try:
            logger.info("digest_send_started")
            response = await asyncio.wait_for(
                _build_and_send_digest(started), timeout=_DIGEST_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error("digest_send_timeout timeout=%ds", _DIGEST_TIMEOUT)
            return DigestResponse(
                status="failed",
                message=f"Digest send timed out after {_DIGEST_TIMEOUT}s",
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )
        except Exception:
            logger.exception("digest_send_error")
            return DigestResponse(
                status="failed",
                message="Digest send failed unexpectedly",
                created_at=datetime.now(timezone.utc),
                duration_ms=int((perf_counter() - started) * 1000),
            )

        logger.info(
            "digest_send_finished tickers=%d sent_to=%d duration_ms=%s",
            response.tickers_included,
            response.sent_to,
            int((perf_counter() - started) * 1000),
        )
        return response
