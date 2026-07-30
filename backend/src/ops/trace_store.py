"""
Trace persistence for the ops dashboard.

Saves full agent traces (tool calls, debate turns, timings, correlation IDs)
to PostgreSQL. Supports querying by ticker, time range, or correlation ID,
and replay (ordered events for a given trace).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.db import execute, fetch, fetchrow
from src.logging_config import get_logger

log = get_logger("ops.trace_store")


async def save_trace(
    correlation_id: str,
    ticker: str,
    duration_ms: float,
    status: str,
    events: list[dict[str, Any]],
) -> str:
    """
    Persist a complete agent trace to Postgres.

    Args:
        correlation_id: Request/run correlation ID
        ticker: Primary ticker analyzed
        duration_ms: Total trace duration in milliseconds
        status: One of 'success', 'degraded', 'failed'
        events: Ordered list of trace events (tool calls, debate turns, timings)

    Returns:
        The generated trace ID (UUID) on success, empty string on failure.
    """
    trace_id = str(uuid4())

    # Validate duration: reject NaN/inf/negative
    if not math.isfinite(duration_ms) or duration_ms < 0:
        log.warning(
            "trace_save_invalid_duration",
            duration_ms=duration_ms,
            correlation_id=correlation_id,
        )
        return ""

    # Normalize ticker for consistent querying
    normalized_ticker = ticker.upper().strip() if ticker else ticker

    try:
        await execute(
            """
            INSERT INTO ops_traces (id, correlation_id, ticker, created_at, duration_ms, status, events)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            trace_id,
            correlation_id,
            normalized_ticker,
            datetime.now(timezone.utc),
            round(duration_ms),
            status,
            json.dumps(events),
        )
        log.debug("trace_saved", trace_id=trace_id, correlation_id=correlation_id)
    except Exception as exc:
        log.error(
            "trace_save_failed",
            error=type(exc).__name__,
            correlation_id=correlation_id,
            trace_id=trace_id,
        )
        return ""
    return trace_id


async def get_trace_by_id(trace_id: str) -> dict[str, Any] | None:
    """Fetch a single trace by its ID."""
    row = await fetchrow(
        "SELECT * FROM ops_traces WHERE id = $1",
        trace_id,
    )
    return _row_to_dict(row) if row else None


async def get_trace_by_correlation_id(correlation_id: str) -> dict[str, Any] | None:
    """Fetch a trace by correlation/request ID (latest if multiple exist)."""
    row = await fetchrow(
        "SELECT * FROM ops_traces WHERE correlation_id = $1 ORDER BY created_at DESC, id DESC LIMIT 1",
        correlation_id,
    )
    return _row_to_dict(row) if row else None


async def query_traces(
    ticker: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Query traces with optional filters.

    Args:
        ticker: Filter by ticker symbol
        since: Start of time range (inclusive)
        until: End of time range (inclusive)
        status: Filter by status (success/degraded/failed)
        limit: Max results (default 20, max 100)
        offset: Pagination offset
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    conditions = []
    params: list[Any] = []
    param_idx = 1

    if ticker:
        conditions.append(f"ticker = ${param_idx}")
        params.append(ticker.upper().strip())
        param_idx += 1

    if since:
        conditions.append(f"created_at >= ${param_idx}")
        params.append(since)
        param_idx += 1

    if until:
        conditions.append(f"created_at <= ${param_idx}")
        params.append(until)
        param_idx += 1

    if status:
        conditions.append(f"status = ${param_idx}")
        params.append(status)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT id, correlation_id, ticker, created_at, duration_ms, status,
               CASE WHEN jsonb_typeof(events) = 'array' THEN jsonb_array_length(events) ELSE 0 END as event_count
        FROM ops_traces
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([limit, offset])

    rows = await fetch(query, *params)
    return [
        {
            "id": str(row["id"]),
            "correlation_id": row["correlation_id"],
            "ticker": row["ticker"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "duration_ms": row["duration_ms"],
            "status": row["status"],
            "event_count": row["event_count"] or 0,
        }
        for row in rows
    ]


async def get_trace_events(trace_id: str) -> list[dict[str, Any]]:
    """
    Get ordered events for a trace (replay support).

    Returns the full event list in chronological order.
    """
    row = await fetchrow(
        "SELECT events FROM ops_traces WHERE id = $1",
        trace_id,
    )
    if not row:
        return []
    events = row["events"]
    if events is None:
        return []
    # asyncpg returns JSONB as Python objects directly
    if isinstance(events, str):
        return _safe_parse_events(events, trace_id)
    if isinstance(events, list):
        return events
    return []


def _safe_parse_events(raw: str, context_id: str = "") -> list[dict[str, Any]]:
    """Parse JSON string to event list, returning [] on decode failure."""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        log.warning("trace_events_not_array", context_id=context_id)
        return []
    except (json.JSONDecodeError, TypeError):
        log.warning("trace_events_parse_failed", context_id=context_id)
        return []


def _row_to_dict(row) -> dict[str, Any]:
    """Convert an asyncpg Record to a dict with serializable values."""
    events = row["events"]
    if events is None:
        events = []
    elif isinstance(events, str):
        events = _safe_parse_events(events, context_id=str(row["id"]))
    elif not isinstance(events, list):
        events = []
    return {
        "id": str(row["id"]),
        "correlation_id": row["correlation_id"],
        "ticker": row["ticker"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "duration_ms": row["duration_ms"],
        "status": row["status"],
        "events": events,
    }
