"""
Trace replay endpoints for stepping through recorded analyses.

Provides list, detail, SSE replay (with configurable speed), and
a featured trace endpoint for instant demo playback.
"""

import asyncio
import json
import re
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.middleware.auth import limiter
from src.ops.trace_recorder import get_featured_trace, get_trace, list_traces, set_featured_trace

router = APIRouter()
log = structlog.get_logger("replay")

# Speed multipliers: how fast to replay relative to original timing
SPEED_MAP = {
    "1x": 1.0,
    "2x": 0.5,
    "4x": 0.25,
    "instant": 0.0,
}


@router.get("/replay/traces")
@limiter.limit("30/minute")
async def list_replay_traces(
    request: Request,
    ticker: str | None = Query(None, description="Filter by ticker symbol"),
    limit: int = Query(50, ge=1, le=200, description="Max traces to return"),
):
    """List available traces for replay."""
    traces = await list_traces(limit=limit, ticker=ticker)
    return {"traces": traces, "count": len(traces)}


@router.get("/replay/featured")
@limiter.limit("60/minute")
async def get_featured_replay(request: Request):
    """
    Get the curated featured trace for instant demo playback.
    This is the pre-cached NVDA analysis that demonstrates the full pipeline.
    """
    trace = await get_featured_trace()
    if not trace:
        raise HTTPException(status_code=404, detail="No featured trace available")
    return trace


@router.post("/replay/{trace_id}/feature")
@limiter.limit("10/minute")
async def mark_trace_featured(request: Request, trace_id: str):
    """Mark a trace as the featured demo trace (auth required)."""
    try:
        tid = uuid.UUID(trace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trace ID format")

    # Verify trace exists before featuring it
    trace = await get_trace(tid)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    await set_featured_trace(tid)
    return {"status": "ok", "trace_id": str(tid), "is_featured": True}


@router.get("/replay/{trace_id}")
@limiter.limit("30/minute")
async def get_replay_trace(request: Request, trace_id: str):
    """Get a full trace with all events."""
    try:
        tid = uuid.UUID(trace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trace ID format")

    trace = await get_trace(tid)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@router.get("/replay/{trace_id}/stream")
@limiter.limit("20/minute")
async def stream_replay(
    request: Request,
    trace_id: str,
    speed: str = Query("1x", description="Replay speed: 1x, 2x, 4x, or instant"),
):
    """
    SSE endpoint that replays recorded events with configurable speed.

    The events are emitted with the same format as the live analysis stream,
    allowing the frontend to reuse all existing rendering components.
    Speed controls how fast events are replayed relative to original timing.
    """
    try:
        tid = uuid.UUID(trace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trace ID format")

    if speed not in SPEED_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid speed. Must be one of: {', '.join(SPEED_MAP.keys())}",
        )

    trace = await get_trace(tid)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    # Validate trace structure before starting the stream
    events = trace.get("events")
    if not isinstance(events, list):
        raise HTTPException(status_code=500, detail="Trace has invalid event structure")

    speed_factor = SPEED_MAP[speed]

    # Regex for safe SSE event names: alphanumeric, underscores, dots, hyphens
    _safe_event_re = re.compile(r"^[a-zA-Z0-9_.\-]+$")

    async def _replay_generator():
        prev_timestamp = None
        last_seq = 0

        for event in events:
            # Check if client disconnected
            if await request.is_disconnected():
                return

            # Skip heartbeats in replay (they served keep-alive purpose only)
            # but update prev_timestamp to avoid artificial delay accumulation
            if event.get("type") == "heartbeat":
                prev_timestamp = event.get("timestamp", prev_timestamp)
                continue

            # Calculate delay based on original timing
            if speed_factor > 0 and prev_timestamp is not None:
                current_ts = event.get("timestamp", "")
                if current_ts and prev_timestamp:
                    try:
                        curr_dt = datetime.fromisoformat(
                            current_ts.replace("Z", "+00:00") if isinstance(current_ts, str) else ""
                        )
                        prev_dt = datetime.fromisoformat(
                            prev_timestamp.replace("Z", "+00:00") if isinstance(prev_timestamp, str) else ""
                        )
                        delta_ms = (curr_dt - prev_dt).total_seconds() * 1000
                        # Cap individual delays to 5s (some gaps are just heartbeat intervals)
                        delay_ms = min(delta_ms * speed_factor, 5000)
                        if delay_ms > 0:
                            await asyncio.sleep(delay_ms / 1000)
                    except (ValueError, TypeError, AttributeError):
                        # If timestamp parsing fails, use a small fixed delay
                        await asyncio.sleep(0.05 * speed_factor)

                # Re-check disconnect after sleep
                if await request.is_disconnected():
                    return

            prev_timestamp = event.get("timestamp")

            # Sanitize SSE fields to prevent frame injection
            seq = int(event.get("seq", 0)) if str(event.get("seq", 0)).isdigit() else 0
            last_seq = seq
            event_type = event.get("type", "unknown")
            if not _safe_event_re.match(str(event_type)):
                event_type = "unknown"

            data = json.dumps(event)

            yield f"id: {seq}\nevent: {event_type}\ndata: {data}\n\n"

        # Signal replay complete (only reached if not disconnected)
        yield f"id: {last_seq + 1}\nevent: replay_complete\ndata: {json.dumps({'trace_id': str(tid)})}\n\n"

    return StreamingResponse(
        _replay_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
