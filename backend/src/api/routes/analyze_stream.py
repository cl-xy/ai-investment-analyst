"""
SSE streaming endpoint for real-time analysis with agent trace.

Wires together: LangGraph execution → domain events → cost tracking → persistence.
Handles timeouts and real tool latency measurement.
"""

import asyncio
import time

from dotenv import load_dotenv

load_dotenv()

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage

from src.agent.checkpointer import get_checkpointer
from src.agent.concurrency import acquire_analysis_slot, release_analysis_slot
from src.agent.events import EventEmitter
from src.agent.graph import build_graph
from src.api.schemas import VALID_TICKER_RE
from src.api.shutdown import shutdown_coordinator
from src.metrics import metrics
from src.middleware.auth import limiter
from src.middleware.cost_tracker import CostTracker

router = APIRouter()

HEARTBEAT_INTERVAL = 15  # seconds
EXECUTION_TIMEOUT = 120  # max seconds for entire analysis run

# Module-level event store for reconnection (last 5 minutes)
_recent_runs: dict[str, tuple[float, list[str]]] = {}  # run_id -> (timestamp, [sse_strings])
_MAX_RUN_AGE = 300  # 5 minutes
_MAX_STORED_RUNS = 100  # cap total stored runs to prevent unbounded memory growth


def _store_event(run_id: str, sse_msg: str):
    """Store SSE message for potential replay."""
    now = time.time()
    if run_id not in _recent_runs:
        _recent_runs[run_id] = (now, [])
    _recent_runs[run_id] = (now, _recent_runs[run_id][1])
    _recent_runs[run_id][1].append(sse_msg)
    # Evict old runs and enforce max size
    expired = [k for k, (ts, _) in _recent_runs.items() if now - ts > _MAX_RUN_AGE]
    for k in expired:
        del _recent_runs[k]
    # Hard cap: evict oldest by insertion order (Python 3.7+ dicts are ordered)
    while len(_recent_runs) > _MAX_STORED_RUNS:
        del _recent_runs[next(iter(_recent_runs))]


def _replay_events(run_id: str, after_seq: int) -> list[str]:
    """Get stored events after a given sequence number."""
    if run_id not in _recent_runs:
        return []
    _, events = _recent_runs[run_id]
    # Each event has "id: N\n" as first line, parse seq
    result = []
    for ev in events:
        lines = ev.split("\n")
        id_line = next((line for line in lines if line.startswith("id: ")), None)
        if id_line:
            seq = int(id_line.removeprefix("id: "))
            if seq > after_seq:
                result.append(ev)
    return result


async def _heartbeat(emitter: EventEmitter, queue: asyncio.Queue, stop: asyncio.Event):
    """Send periodic heartbeats to keep the SSE connection alive."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL)
            break
        except asyncio.TimeoutError:
            event = emitter.heartbeat()
            await queue.put(event.to_sse())


async def _run_agent(
    tickers: list[str],
    emitter: EventEmitter,
    queue: asyncio.Queue,
    tracker: CostTracker,
    mcp_tools: dict,
):
    """Execute the LangGraph agent and emit domain events to the queue."""

    tickers_upper = [t.upper() for t in tickers]
    tool_start_times: dict[str, float] = {}

    event = emitter.run_started(tickers_upper)
    await queue.put(event.to_sse())

    try:
        message = f"Analyze these stocks: {', '.join(tickers_upper)}"

        graph = build_graph(mcp_tools)

        async with get_checkpointer() as checkpointer:
            compiled = graph.compile(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": f"stream-{emitter.run_id}"}}
            initial_state = {
                "messages": [HumanMessage(content=message)],
                "tickers_to_analyze": tickers_upper,
            }

            current_node = None

            # Wrap the entire execution in a timeout
            async def _execute():
                nonlocal current_node

                async for event_data in compiled.astream_events(
                    initial_state, config=config, version="v2"
                ):
                    kind = event_data.get("event")
                    name = event_data.get("name", "")
                    data = event_data.get("data", {})

                    # Node lifecycle
                    if kind == "on_chain_start" and name in (
                        "router",
                        "fetch_data",
                        "analyze_ticker",
                        "generate_report",
                        "compare",
                        "chat",
                        "portfolio_ops",
                    ):
                        if current_node:
                            ev = emitter.node_completed(current_node)
                            await queue.put(ev.to_sse())
                        current_node = name
                        ev = emitter.node_started(name)
                        await queue.put(ev.to_sse())

                    # Tool start: record timestamp for duration
                    elif kind == "on_tool_start":
                        tool_name = name
                        # Use run_id from event to handle concurrent same-name tool calls
                        tool_run_id = event_data.get("run_id", tool_name)
                        tool_start_times[tool_run_id] = (time.monotonic(), tool_name)
                        tool_input = data.get("input", {})
                        ev = emitter.tool_call(tool_name, tool_input, node=current_node)
                        await queue.put(ev.to_sse())

                    # Tool end: compute real duration
                    elif kind == "on_tool_end":
                        tool_name = name
                        tool_run_id = event_data.get("run_id", tool_name)
                        start_entry = tool_start_times.pop(tool_run_id, None)
                        if start_entry:
                            tool_start, _ = start_entry
                        else:
                            tool_start = time.monotonic()
                        duration_ms = int((time.monotonic() - tool_start) * 1000)
                        output = data.get("output", "")
                        success = "error" not in str(output).lower()[:100]

                        # Heuristic: sub-50ms responses are cache hits
                        # (real yfinance/newsapi/sec calls take 200ms+)
                        is_cached = duration_ms < 50

                        # Record in cost tracker
                        tracker.record_tool_call(success=success, cached=is_cached)

                        # Record in metrics
                        metrics.inc("tool_calls_total", labels={"tool": tool_name, "status": "success" if success else "error"})
                        metrics.observe("tool_call_duration_seconds", duration_ms / 1000, labels={"tool": tool_name})

                        ev = emitter.tool_result(
                            tool_name,
                            success=success,
                            cached=is_cached,
                            duration_ms=duration_ms,
                            source_id=f"{tool_name}:{int(time.time())}",
                            node=current_node,
                        )
                        await queue.put(ev.to_sse())

                    # LLM token streaming
                    elif kind == "on_chat_model_stream":
                        chunk = data.get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            ev = emitter.llm_token(chunk.content, node=current_node)
                            await queue.put(ev.to_sse())

                    # LLM completion: track tokens
                    elif kind == "on_chat_model_end":
                        output = data.get("output")
                        if output and hasattr(output, "usage_metadata"):
                            usage = output.usage_metadata
                            if usage:
                                tracker.record_tokens(
                                    prompt=usage.get("input_tokens", 0),
                                    completion=usage.get("output_tokens", 0),
                                )
                        metrics.inc("llm_calls_total")

            try:
                await asyncio.wait_for(_execute(), timeout=EXECUTION_TIMEOUT)
            except asyncio.TimeoutError:
                ev = emitter.error(
                    f"Analysis timed out after {EXECUTION_TIMEOUT}s",
                    recoverable=False,
                    context="execution_timeout",
                )
                await queue.put(ev.to_sse())

            # Close final node
            if current_node:
                ev = emitter.node_completed(current_node)
                await queue.put(ev.to_sse())

            # Get final state for analysis results
            final_state = await compiled.aget_state(config)
            state_values = final_state.values if final_state else {}
            ticker_analyses = state_values.get("ticker_analyses", {})

            for ticker, analysis in ticker_analyses.items():
                ev = emitter.analysis_complete(ticker, analysis)
                await queue.put(ev.to_sse())

                # Track schema quality
                citations_count = len(analysis.get("citations", []))
                data_gaps_count = len(analysis.get("data_gaps", []))
                tracker.record_schema_result(
                    valid=True, citations=citations_count, data_gaps=data_gaps_count
                )

    except Exception as exc:
        metrics.inc("analyses_total", labels={"status": "error"})
        ev = emitter.error(str(exc), recoverable=False, context="agent_execution")
        await queue.put(ev.to_sse())
        _run_succeeded = False
    else:
        metrics.inc("analyses_total", labels={"status": "success"})
        _run_succeeded = True

    # Always emit run_completed and signal done, even if summary/persist fail
    try:
        summary = tracker.summary()

        if _run_succeeded:
            metrics.observe("analysis_duration_seconds", summary["total_duration_ms"] / 1000)

        ev = emitter.run_completed(
            tickers_upper,
            total_duration_ms=summary["total_duration_ms"],
            total_tokens=summary["total_tokens"],
            cost_usd=summary["cost_usd"],
        )
        await queue.put(ev.to_sse())

        # Persist run metrics to PostgreSQL
        try:
            await tracker.persist()
        except Exception:
            pass  # Non-critical, don't break the stream for persistence failure
    except Exception:
        pass  # Don't let summary/emit failures prevent stream termination
    finally:
        # Signal done (must always fire so _stream_generator exits cleanly)
        await queue.put(None)


async def _stream_generator(
    tickers: list[str],
    request: Request,
    last_event_id: int | None = None,
    resume_run_id: str | None = None,
):
    """Async generator that yields SSE events."""
    # If reconnecting, try to replay missed events
    if last_event_id is not None and resume_run_id:
        replayed = _replay_events(resume_run_id, last_event_id)
        for ev in replayed:
            yield ev
        if replayed:
            # Check if run already completed
            _, stored = _recent_runs.get(resume_run_id, (0, []))
            if any("run_completed" in ev for ev in stored):
                # Release the slot before returning (acquired by caller)
                release_analysis_slot()
                return  # Run finished, nothing to stream

    emitter = EventEmitter()
    queue: asyncio.Queue = asyncio.Queue()
    stop_heartbeat = asyncio.Event()
    tracker = CostTracker(run_id=emitter.run_id, tickers=tickers)

    agent_task = asyncio.create_task(_run_agent(tickers, emitter, queue, tracker, request.app.state.mcp_tools))
    shutdown_coordinator.register(agent_task)
    heartbeat_task = asyncio.create_task(_heartbeat(emitter, queue, stop_heartbeat))

    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                msg = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if msg is None:
                break

            yield msg
            _store_event(emitter.run_id, msg)

    finally:
        stop_heartbeat.set()
        agent_task.cancel()
        heartbeat_task.cancel()
        try:
            await agent_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await heartbeat_task
        except (asyncio.CancelledError, Exception):
            pass
        release_analysis_slot()


@router.get("/analyze/stream")
@limiter.limit("10/minute")
async def analyze_stream(
    request: Request,
    tickers: str = Query(..., description="Comma-separated ticker symbols"),
):
    """
    SSE endpoint for streaming analysis with full agent trace.

    Features:
    - Domain-specific events (not raw LangGraph internals)
    - Real tool latency measurement
    - Cost/token tracking persisted to PostgreSQL
    - 120s execution timeout with graceful error event
    - 15s heartbeat to prevent proxy buffering
    - Input validation (alphanumeric, max 5 tickers)
    - Graceful shutdown: rejects new requests when draining
    - Concurrency limiter: max 3 concurrent analysis pipelines
    """
    # Reject new streams during shutdown drain
    if shutdown_coordinator.is_draining:
        return JSONResponse(
            status_code=503,
            content={"error": "Server is shutting down, try again shortly"},
            headers={"Retry-After": "10"},
        )

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return JSONResponse(
            status_code=400,
            content={"detail": "At least one ticker is required"},
        )

    valid_pattern = VALID_TICKER_RE
    invalid = [t for t in ticker_list if not valid_pattern.match(t)]
    if invalid:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Invalid ticker symbols: {', '.join(invalid)}"},
        )

    if len(ticker_list) > 5:
        return JSONResponse(
            status_code=400,
            content={"detail": "Maximum 5 tickers per analysis request"},
        )

    # Acquire concurrency slot
    slot_acquired = await acquire_analysis_slot()
    if not slot_acquired:
        return JSONResponse(
            status_code=503,
            content={"error": "Server at capacity, please retry in a few seconds"},
            headers={"Retry-After": "5"},
        )

    # Check for reconnection (parse safely to avoid slot leak on bad header)
    last_event_id_header = request.headers.get("Last-Event-ID")
    last_event_id: int | None = None
    if last_event_id_header:
        try:
            last_event_id = int(last_event_id_header)
        except (ValueError, TypeError):
            release_analysis_slot()
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid Last-Event-ID header"},
            )
    resume_run_id = request.headers.get("X-Run-ID")  # Client sends this on reconnect

    return StreamingResponse(
        _stream_generator(
            ticker_list,
            request,
            last_event_id=last_event_id,
            resume_run_id=resume_run_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
