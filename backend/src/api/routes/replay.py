"""
Trace replay endpoints for stepping through recorded analyses.

Provides list, detail, SSE replay (with configurable speed), and
a featured trace endpoint for instant demo playback.
"""

import asyncio
import json
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.middleware.auth import limiter
from src.ops.trace_recorder import get_featured_trace, get_trace, list_traces

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

    speed_factor = SPEED_MAP[speed]

    async def _replay_generator():
        events = trace["events"]
        prev_timestamp = None

        for event in events:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            # Skip heartbeats in replay (they served keep-alive purpose only)
            if event.get("type") == "heartbeat":
                continue

            # Calculate delay based on original timing
            if speed_factor > 0 and prev_timestamp is not None:
                current_ts = event.get("timestamp", "")
                if current_ts and prev_timestamp:
                    try:
                        from datetime import datetime

                        curr_dt = datetime.fromisoformat(current_ts.replace("Z", "+00:00"))
                        prev_dt = datetime.fromisoformat(prev_timestamp.replace("Z", "+00:00"))
                        delta_ms = (curr_dt - prev_dt).total_seconds() * 1000
                        # Cap individual delays to 5s (some gaps are just heartbeat intervals)
                        delay_ms = min(delta_ms * speed_factor, 5000)
                        if delay_ms > 0:
                            await asyncio.sleep(delay_ms / 1000)
                    except (ValueError, TypeError):
                        # If timestamp parsing fails, use a small fixed delay
                        await asyncio.sleep(0.05 * speed_factor)

            prev_timestamp = event.get("timestamp")

            # Emit as SSE in the same format as live stream
            seq = event.get("seq", 0)
            event_type = event.get("type", "unknown")
            data = json.dumps(event)

            yield f"id: {seq}\nevent: {event_type}\ndata: {data}\n\n"

        # Signal replay complete
        yield f"event: replay_complete\ndata: {json.dumps({'trace_id': str(tid)})}\n\n"

    return StreamingResponse(
        _replay_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
