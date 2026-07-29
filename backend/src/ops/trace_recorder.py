"""
Trace recorder: captures complete SSE event sequences for replay.

Hooks into the streaming pipeline to persist all domain events with timestamps
to PostgreSQL. Supports marking a trace as "featured" for instant demo playback.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import structlog

from src.db import get_pool

log = structlog.get_logger("trace_recorder")


async def record_trace(
    run_id: str,
    tickers: list[str],
    events: list[dict],
    duration_ms: int,
    status: str,
    signal: str | None = None,
) -> uuid.UUID:
    """
    Persist a complete trace (all SSE events) to PostgreSQL.

    Args:
        run_id: The analysis run UUID.
        tickers: List of ticker symbols analyzed.
        events: List of event dicts (the full SSE payloads).
        duration_ms: Total analysis duration in milliseconds.
        status: One of 'success', 'degraded', 'failed'.
        signal: Final signal for single-ticker analyses (buy/hold/sell).

    Returns:
        The generated trace UUID.
    """
    trace_id = uuid.uuid4()
    pool = await get_pool()

    try:
        await pool.execute(
            """
            INSERT INTO traces (
                id, run_id, tickers, events, duration_ms, status, signal, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            trace_id,
            run_id,
            tickers,
            json.dumps(events),
            duration_ms,
            status,
            signal,
            datetime.now(timezone.utc),
        )
        log.info("trace_recorded", trace_id=str(trace_id), tickers=tickers, status=status)
    except Exception as exc:
        log.warning("trace_record_failed", error=str(exc), run_id=run_id)
        raise

    return trace_id


async def set_featured_trace(trace_id: uuid.UUID) -> None:
    """Mark a trace as the featured demo trace (only one at a time)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Clear existing featured flag
            await conn.execute("UPDATE traces SET is_featured = FALSE WHERE is_featured = TRUE")
            # Set new featured
            await conn.execute("UPDATE traces SET is_featured = TRUE WHERE id = $1", trace_id)
    log.info("featured_trace_set", trace_id=str(trace_id))


async def get_featured_trace() -> dict | None:
    """Get the featured trace for instant demo playback."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, run_id, tickers, events, duration_ms, status, signal, created_at
        FROM traces
        WHERE is_featured = TRUE
        LIMIT 1
        """
    )
    if not row:
        return None
    return _row_to_trace(row)


async def get_trace(trace_id: uuid.UUID) -> dict | None:
    """Get a single trace by ID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, run_id, tickers, events, duration_ms, status, signal, created_at
        FROM traces
        WHERE id = $1
        """,
        trace_id,
    )
    if not row:
        return None
    return _row_to_trace(row)


async def list_traces(limit: int = 50, ticker: str | None = None) -> list[dict]:
    """List available traces, newest first. Optionally filter by ticker."""
    pool = await get_pool()

    if ticker:
        rows = await pool.fetch(
            """
            SELECT id, run_id, tickers, duration_ms, status, signal, created_at, is_featured
            FROM traces
            WHERE $1 = ANY(tickers)
            ORDER BY created_at DESC
            LIMIT $2
            """,
            ticker.upper(),
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, run_id, tickers, duration_ms, status, signal, created_at, is_featured
            FROM traces
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )

    return [_row_to_trace_summary(row) for row in rows]


def _row_to_trace(row) -> dict:
    """Convert a DB row to a full trace dict (with events)."""
    events_raw = row["events"]
    events = json.loads(events_raw) if isinstance(events_raw, str) else events_raw
    return {
        "id": str(row["id"]),
        "run_id": row["run_id"],
        "tickers": row["tickers"],
        "events": events,
        "duration_ms": row["duration_ms"],
        "status": row["status"],
        "signal": row["signal"],
        "created_at": row["created_at"].isoformat(),
    }


def _row_to_trace_summary(row) -> dict:
    """Convert a DB row to a trace summary dict (no events)."""
    return {
        "id": str(row["id"]),
        "run_id": row["run_id"],
        "tickers": row["tickers"],
        "duration_ms": row["duration_ms"],
        "status": row["status"],
        "signal": row["signal"],
        "created_at": row["created_at"].isoformat(),
        "is_featured": row.get("is_featured", False),
    }
