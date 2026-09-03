"""
SSE streaming endpoint for real-time analysis with agent trace.

Wires together: LangGraph execution → domain events → cost tracking → persistence.
Handles timeouts and real tool latency measurement.
"""

import asyncio
import json
import os
import time
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage

from src.agent.checkpointer import get_checkpointer
from src.agent.concurrency import acquire_analysis_slot, release_analysis_slot
from src.agent.debate_schemas import DEBATE_ROLES
from src.agent.events import EventEmitter, EventType, StreamEvent
from src.agent.graph import build_graph
from src.agent.json_utils import extract_json
from src.agent.nodes.debate import _dedup_text
from src.api.schemas import VALID_TICKER_RE
from src.api.shutdown import shutdown_coordinator
from src.logging_config import request_id_ctx
from src.metrics import metrics
from src.middleware.auth import limiter
from src.middleware.cost_tracker import CostTracker
from src.ops.collector import collector
from src.ops.cost_attribution import cost_attributor

router = APIRouter()

HEARTBEAT_INTERVAL = 15  # seconds
EXECUTION_TIMEOUT_PER_TICKER = (
    180  # seconds per ticker for debate (free tier LLMs: 30-73s x3 calls + report)
)
EXECUTION_TIMEOUT_BASE = 30  # base overhead (graph setup, data fetch)

# Module-level event store for reconnection (last 5 minutes)
_recent_runs: dict[str, tuple[float, list[str]]] = {}  # run_id -> (timestamp, [sse_strings])
_MAX_RUN_AGE = 300  # 5 minutes
_MAX_STORED_RUNS = 100  # cap total stored runs to prevent unbounded memory growth
_EVICT_INTERVAL = 30  # seconds between eviction sweeps
_last_eviction: float = 0.0

# In-flight ticker deduplication: prevents duplicate LLM pipeline spend when
# multiple requests arrive for the same ticker set concurrently.
_in_flight_tickers: set[str] = set()


def _store_event(run_id: str, sse_msg: str):
    """Store SSE message for potential replay."""
    global _last_eviction
    now = time.time()
    if run_id not in _recent_runs:
        _recent_runs[run_id] = (now, [])
    else:
        # Pop and re-insert to move to end (maintain LRU order for eviction)
        _recent_runs[run_id] = _recent_runs.pop(run_id)
    _recent_runs[run_id] = (now, _recent_runs[run_id][1])
    _recent_runs[run_id][1].append(sse_msg)
    # Evict expired/overflow only periodically, not on every event
    if now - _last_eviction > _EVICT_INTERVAL:
        _last_eviction = now
        expired = [k for k, (ts, _) in _recent_runs.items() if now - ts > _MAX_RUN_AGE]
        for k in expired:
            del _recent_runs[k]
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
            try:
                seq = int(id_line.removeprefix("id: "))
            except (ValueError, TypeError):
                continue
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
    tool_start_times: dict[str, tuple[float, str]] = {}
    # Track debate LLM calls within the debate node
    debate_llm_count: dict[str, int] = defaultdict(int)
    debate_llm_start: dict[str, float] = {}  # per-ticker start times
    correlation_id = emitter.correlation_id

    # Initialize per-ticker cost attribution tracking
    for t in tickers_upper:
        cost_attributor.start_analysis(t)

    event = emitter.run_started(tickers_upper)
    await queue.put(event.to_sse())

    ticker_analyses: dict = {}
    _run_succeeded = False
    _timed_out = False

    try:
        message = f"Analyze these stocks: {', '.join(tickers_upper)}"

        graph = build_graph(mcp_tools)

        async with get_checkpointer() as checkpointer:
            compiled = graph.compile(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": f"stream-{emitter.run_id}"}}
            initial_state = {
                "messages": [HumanMessage(content=message)],
                "tickers_to_analyze": tickers_upper,
                "intent": "single_ticker" if len(tickers_upper) == 1 else "full_report",
                "correlation_id": correlation_id,
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
                        "debate",
                        "peer_compare",
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
                        output_str = str(output).lower()[:200]
                        success = "error" not in output_str

                        # Distinguish "no data available" from genuine errors
                        no_data = not success and any(
                            phrase in output_str
                            for phrase in (
                                "no filings found",
                                "not found",
                                "no data",
                                "unavailable",
                            )
                        )

                        # Heuristic: sub-50ms responses are cache hits
                        # (real yfinance/newsapi/sec calls take 200ms+)
                        is_cached = duration_ms < 50

                        # Record in cost tracker
                        tracker.record_tool_call(success=success, cached=is_cached)

                        # Record in metrics
                        metrics.inc(
                            "tool_calls_total",
                            labels={"tool": tool_name, "status": "success" if success else "error"},
                        )
                        metrics.observe(
                            "tool_call_duration_seconds",
                            duration_ms / 1000,
                            labels={"tool": tool_name},
                        )

                        ev = emitter.tool_result(
                            tool_name,
                            success=success,
                            cached=is_cached,
                            duration_ms=duration_ms,
                            source_id=f"{tool_name}:{int(time.time())}",
                            node=current_node,
                            no_data=no_data,
                        )
                        await queue.put(ev.to_sse())

                    # LLM token streaming
                    elif kind == "on_chat_model_stream":
                        chunk = data.get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            ev = emitter.llm_token(chunk.content, node=current_node)
                            await queue.put(ev.to_sse())

                    # LLM start: track debate timing (keyed by current_node context)
                    elif kind == "on_chat_model_start":
                        if current_node == "debate":
                            # Store start time keyed by LLM call run_id
                            llm_run_id = event_data.get("run_id", "_pending")
                            debate_llm_start[llm_run_id] = time.monotonic()

                    # LLM completion: track tokens + emit debate events
                    elif kind == "on_chat_model_end":
                        output = data.get("output")
                        _input_tokens = 0
                        _output_tokens = 0
                        if output and hasattr(output, "usage_metadata"):
                            usage = output.usage_metadata
                            if usage:
                                _input_tokens = usage.get("input_tokens", 0)
                                _output_tokens = usage.get("output_tokens", 0)
                                tracker.record_tokens(
                                    prompt=_input_tokens,
                                    completion=_output_tokens,
                                )
                        metrics.inc("llm_calls_total")

                        # Per-ticker cost attribution: attribute LLM call to
                        # the appropriate ticker based on current node context.
                        _attr_model_type = "router" if current_node == "router" else "analysis"
                        # Use fallback estimates when provider doesn't report usage
                        if not _input_tokens and not _output_tokens:
                            if current_node == "router":
                                _input_tokens, _output_tokens = 1500, 500
                            elif current_node == "debate":
                                _input_tokens, _output_tokens = 3000, 2000
                            else:
                                _input_tokens, _output_tokens = 4000, 3000

                        # For non-debate nodes, split cost evenly across tickers
                        if current_node != "debate" and tickers_upper:
                            _split_input = _input_tokens // len(tickers_upper)
                            _split_output = _output_tokens // len(tickers_upper)
                            for _t in tickers_upper:
                                cost_attributor.record_llm_call(
                                    ticker=_t,
                                    model_type=_attr_model_type,
                                    input_tokens=_split_input,
                                    output_tokens=_split_output,
                                )

                        # Emit debate turn events when inside the debate node
                        if current_node == "debate" and output and hasattr(output, "content"):
                            # Identify which ticker this LLM call belongs to by
                            # parsing the ticker field from the JSON output.
                            _current_ticker = None
                            try:
                                parsed_output = extract_json(output.content)
                                if isinstance(parsed_output, dict):
                                    resp_ticker = parsed_output.get("ticker", "").upper()
                                    if resp_ticker in tickers_upper:
                                        _current_ticker = resp_ticker
                            except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
                                pass

                            # Fallback: use the ticker currently being debated.
                            # The debate node processes one ticker at a time (the
                            # first in tickers_to_analyze not yet in ticker_analyses).
                            # Previous fallback used a sequential counter which could
                            # misattribute retry events to the wrong ticker.
                            _num_debate_turns = len(DEBATE_ROLES)
                            if not _current_ticker:
                                # Find the ticker currently being debated: first one
                                # that hasn't completed all expected debate turns yet.
                                analyzed_tickers = [
                                    t
                                    for t in tickers_upper
                                    if debate_llm_count[t] >= _num_debate_turns
                                ]
                                for t in tickers_upper:
                                    if t not in analyzed_tickers:
                                        _current_ticker = t
                                        break

                            if not _current_ticker:
                                # All tickers already have their turns; this is a stray
                                # retry event. Skip it entirely.
                                llm_run_id = event_data.get("run_id", "_pending")
                                debate_llm_start.pop(llm_run_id, None)
                                continue

                            count = debate_llm_count[_current_ticker]
                            # Only advance the counter up to the expected number of
                            # debate roles. Extra calls from retries are ignored.
                            if count >= _num_debate_turns:
                                llm_run_id = event_data.get("run_id", "_pending")
                                debate_llm_start.pop(llm_run_id, None)
                                continue

                            llm_run_id = event_data.get("run_id", "_pending")
                            duration_ms = int(
                                (
                                    time.monotonic()
                                    - debate_llm_start.pop(llm_run_id, time.monotonic())
                                )
                                * 1000
                            )

                            try:
                                turn_data = extract_json(output.content)
                            except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
                                turn_data = {}
                            if not isinstance(turn_data, dict):
                                turn_data = {}

                            # Skip events from failed LLM attempts (retries).
                            # A valid debate turn must have a thesis; if missing,
                            # this is likely a malformed first attempt that will
                            # be retried by the debate node. Don't consume the
                            # role slot with invalid data.
                            if not turn_data.get("thesis"):
                                continue

                            debate_llm_count[_current_ticker] = count + 1

                            # Record debate LLM cost against this ticker
                            cost_attributor.record_llm_call(
                                ticker=_current_ticker,
                                model_type="analysis",
                                input_tokens=_input_tokens,
                                output_tokens=_output_tokens,
                                duration_ms=duration_ms,
                            )

                            role = DEBATE_ROLES[min(count, _num_debate_turns - 1)]

                            if count == 0:
                                ev = emitter.debate_started(_current_ticker, list(DEBATE_ROLES))
                                await queue.put(ev.to_sse())

                            # Emit debate turn for all roles
                            key_args = (
                                turn_data.get("bull_case", []) + turn_data.get("bear_case", [])
                                if count == _num_debate_turns - 1
                                else turn_data.get("key_arguments", [])
                            )
                            ev = emitter.debate_turn(
                                ticker=_current_ticker,
                                role=role,
                                thesis=_dedup_text(turn_data.get("thesis", "")),
                                confidence=turn_data.get("confidence", "medium"),
                                key_arguments=key_args,
                                turn_index=count,
                                duration_ms=duration_ms,
                            )
                            await queue.put(ev.to_sse())

                            # Moderator (last role) also produces the verdict
                            if count == _num_debate_turns - 1:
                                ev = emitter.debate_verdict(
                                    ticker=_current_ticker,
                                    signal=turn_data.get("signal", "hold"),
                                    confidence=turn_data.get("confidence", "medium"),
                                    verdict_rationale=_dedup_text(
                                        turn_data.get("verdict_rationale", "")
                                    ),
                                    key_disagreements=turn_data.get("key_disagreements", []),
                                    duration_ms=duration_ms,
                                )
                                await queue.put(ev.to_sse())

            # Scale timeout with ticker count: each ticker's debate takes ~100s
            execution_timeout = EXECUTION_TIMEOUT_BASE + (
                len(tickers_upper) * EXECUTION_TIMEOUT_PER_TICKER
            )

            _timeout_stage: str | None = None
            _run_start = time.monotonic()

            try:
                await asyncio.wait_for(_execute(), timeout=execution_timeout)
            except asyncio.TimeoutError:
                _timed_out = True
                _timeout_stage = current_node

            # Close final node
            if current_node:
                ev = emitter.node_completed(current_node)
                await queue.put(ev.to_sse())

            # Get final state for analysis results. Read this BEFORE emitting the
            # timeout event so we can tell the client which tickers actually
            # finished vs which still need a retry — a checkpointed LangGraph run
            # may have completed some tickers before the timeout fired.
            final_state = await compiled.aget_state(config)
            state_values = final_state.values if final_state else {}
            ticker_analyses = state_values.get("ticker_analyses", {})

            if _timed_out:
                completed = [t for t in tickers_upper if t in ticker_analyses]
                incomplete = [t for t in tickers_upper if t not in ticker_analyses]
                elapsed = time.monotonic() - _run_start

                # Debate/report stages are LLM-bound and transient (rate limits,
                # slow free-tier inference) — safe to retry soon. Data-fetch stage
                # timeouts more often indicate an upstream provider outage, so
                # give it more breathing room before the client retries.
                retry_after = 15 if _timeout_stage in ("debate", "generate_report") else 45

                metrics.inc(
                    "analysis_timeouts_total",
                    labels={
                        "stage": _timeout_stage or "unknown",
                        "ticker_count": str(len(tickers_upper)),
                    },
                )

                ev = emitter.analysis_timeout(
                    completed_tickers=completed,
                    incomplete_tickers=incomplete,
                    stage=_timeout_stage,
                    elapsed_seconds=elapsed,
                    retry_after_seconds=retry_after,
                )
                await queue.put(ev.to_sse())

            for ticker, analysis in ticker_analyses.items():
                # Strip internal debate fields from SSE payload
                clean_analysis = {k: v for k, v in analysis.items() if not k.startswith("_")}
                ev = emitter.analysis_complete(ticker, clean_analysis)
                await queue.put(ev.to_sse())

                # Track schema quality
                citations_count = len(analysis.get("citations", []))
                data_gaps_count = len(analysis.get("data_gaps", []))
                tracker.record_schema_result(
                    valid=True, citations=citations_count, data_gaps=data_gaps_count
                )

                # Flush per-ticker cost attribution to PostgreSQL
                try:
                    await cost_attributor.flush(ticker, correlation_id=correlation_id)
                except Exception:
                    pass  # Non-critical, don't break the stream

            peer_comparison = state_values.get("peer_comparison")
            if peer_comparison:
                ev = emitter.peer_comparison_ready(peer_comparison)
                await queue.put(ev.to_sse())

            # Persist analyses + record predictions (non-blocking)
            if ticker_analyses:
                try:
                    from src.api.persistence import persist_full_run

                    report_md = state_values.get("report_markdown", "")
                    await persist_full_run(
                        tickers_upper, ticker_analyses, report_md, correlation_id=correlation_id
                    )
                except Exception as persist_err:
                    import logging as _logging

                    _logging.getLogger("analyze_stream").warning(
                        "Persistence failed: %s", persist_err
                    )

                # Persist evidence artifacts and citation validations
                run_evidence = state_values.get("run_evidence")
                if run_evidence:
                    try:
                        from src.evidence.registry import (
                            persist_citation_validation,
                            persist_run_evidence,
                        )

                        await persist_run_evidence(run_evidence)

                        # Persist citation validation for each ticker
                        for _tk, _analysis in ticker_analyses.items():
                            cv = _analysis.get("_citation_validation")
                            if cv:
                                await persist_citation_validation(
                                    run_id=correlation_id or "unknown",
                                    results=cv.get("results", []),
                                    confidence_multiplier=cv.get("confidence_multiplier", 1.0),
                                    original_confidence=cv.get("original_confidence", ""),
                                    adjusted_confidence=cv.get(
                                        "adjusted_confidence", cv.get("original_confidence", "")
                                    ),
                                )
                    except Exception as ev_err:
                        import logging as _logging

                        _logging.getLogger("analyze_stream").warning(
                            "Evidence persistence failed: %s", ev_err
                        )

    except Exception as exc:
        metrics.inc("analyses_total", labels={"status": "error"})
        ev = emitter.error(str(exc), recoverable=False, context="agent_execution")
        await queue.put(ev.to_sse())
        _run_succeeded = False
    else:
        if _timed_out:
            metrics.inc("analyses_total", labels={"status": "error"})
            _run_succeeded = False
        else:
            metrics.inc("analyses_total", labels={"status": "success"})
            _run_succeeded = True

    # Always emit run_completed and signal done, even if summary/persist fail
    try:
        summary = tracker.summary()

        # Record duration for ALL analyses (success + timeout + error)
        duration_s = summary["total_duration_ms"] / 1000
        outcome = "success" if _run_succeeded else "timeout" if _timed_out else "error"
        metrics.observe("analysis_duration_seconds", duration_s, labels={"status": outcome})

        # Also record to ops collector so /ops dashboard shows activity
        collector.record_request(
            endpoint="/api/analyze/stream",
            status_code=200 if _run_succeeded else 504 if _timed_out else 500,
            duration_ms=summary["total_duration_ms"],
        )

        # Flush cost attribution for all started tickers (even on timeout)
        for ticker in tickers_upper:
            try:
                await cost_attributor.flush(ticker, correlation_id=correlation_id)
            except Exception:
                pass

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

        # Record trace for replay system (non-blocking)
        try:
            from src.ops.trace_recorder import record_trace

            # Determine final signal from first ticker analysis
            final_signal = None
            if ticker_analyses:
                first_analysis: dict = next(iter(ticker_analyses.values()), {})
                final_signal = first_analysis.get("signal")

            status = "success" if _run_succeeded else "failed"
            # Check for degraded state (some tools failed but analysis completed)
            if _run_succeeded and any(
                e.payload.get("no_data") for e in emitter.events if e.type.value == "tool_result"
            ):
                status = "degraded"

            await record_trace(
                run_id=emitter.run_id,
                tickers=tickers_upper,
                events=[e.model_dump() for e in emitter.events],
                duration_ms=summary["total_duration_ms"],
                status=status,
                signal=final_signal,
            )
        except Exception:
            pass  # Trace recording is non-critical
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
    flight_key: str | None = None,
):
    """Async generator that yields SSE events."""
    slot_released = False

    # If reconnecting, try to replay missed events
    if last_event_id is not None and resume_run_id:
        replayed = _replay_events(resume_run_id, last_event_id)
        if not replayed and resume_run_id not in _recent_runs:
            # Run state not found on this instance (likely routed to different machine).
            # Emit a terminal error so the client stops reconnecting blindly.
            from datetime import datetime, timezone

            error_event = StreamEvent(
                run_id=resume_run_id,
                seq=last_event_id + 1 if last_event_id else 1,
                type=EventType.ERROR,
                timestamp=datetime.now(timezone.utc).isoformat(),
                payload={
                    "message": "Run state unavailable on this instance. Please start a new analysis.",
                    "recoverable": False,
                },
            )
            yield error_event.to_sse()
            # No slot to release: reconnections don't acquire analysis slots
            slot_released = True
            return
        for ev in replayed:
            yield ev
        if replayed:
            # Check if run already completed
            _, stored = _recent_runs.get(resume_run_id, (0, []))
            if any("run_completed" in ev for ev in stored):
                slot_released = True
                return  # Run finished, nothing to stream
            # Run still in progress; client got replayed events but we cannot
            # attach to the live run from here. Do NOT start a new agent.
            slot_released = True
            return
        else:
            # Run exists on this instance but client already has all events.
            # Check if the run completed (emit terminal) or is still in-progress
            # (emit completed event). Either way, do NOT start a duplicate task.
            _, stored = _recent_runs.get(resume_run_id, (0, []))
            if any("run_completed" in ev for ev in stored):
                # Run already finished, client is caught up
                slot_released = True
                return
            # Run still in progress but no new events yet — tell client to wait
            # rather than spawning a duplicate analysis
            from datetime import datetime, timezone

            heartbeat_event = StreamEvent(
                run_id=resume_run_id,
                seq=last_event_id + 1 if last_event_id else 1,
                type=EventType.HEARTBEAT,
                timestamp=datetime.now(timezone.utc).isoformat(),
                payload={"message": "Reconnected, waiting for new events"},
            )
            yield heartbeat_event.to_sse()
            slot_released = True
            return

    # Capture correlation_id from request middleware context var
    correlation_id = request_id_ctx.get() or None
    emitter = EventEmitter(correlation_id=correlation_id)
    queue: asyncio.Queue = asyncio.Queue()
    stop_heartbeat = asyncio.Event()
    tracker = CostTracker(run_id=emitter.run_id, tickers=tickers)

    agent_task: asyncio.Task | None = None
    heartbeat_task: asyncio.Task | None = None

    try:
        # flight_key already registered in _in_flight_tickers by analyze_stream()

        agent_task = asyncio.create_task(
            _run_agent(tickers, emitter, queue, tracker, request.app.state.mcp_tools)
        )
        shutdown_coordinator.register(agent_task)
        heartbeat_task = asyncio.create_task(_heartbeat(emitter, queue, stop_heartbeat))

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
        if agent_task is not None:
            agent_task.cancel()
            try:
                await agent_task
            except (asyncio.CancelledError, Exception):
                pass
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
        # Release singleflight tracking so subsequent requests can proceed
        if flight_key:
            _in_flight_tickers.discard(flight_key)
        if not slot_released:
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

    ticker_list = list(dict.fromkeys(t.strip().upper() for t in tickers.split(",") if t.strip()))
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

    if len(ticker_list) > 4:
        return JSONResponse(
            status_code=400,
            content={"detail": "Maximum 4 tickers per streaming analysis request"},
        )

    # Check for reconnection BEFORE slot acquisition so replay-only requests
    # don't consume analysis slots. Reconnections replay cached events without
    # running agent tasks, so they must not hold scarce execution capacity.
    last_event_id_header = request.headers.get("Last-Event-ID") or request.query_params.get(
        "last_event_id"
    )
    last_event_id: int | None = None
    if last_event_id_header:
        try:
            last_event_id = int(last_event_id_header)
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid Last-Event-ID header"},
            )
    resume_run_id = request.headers.get("X-Run-ID") or request.query_params.get(
        "run_id"
    )  # Client sends this on reconnect

    is_reconnection = last_event_id is not None and resume_run_id is not None

    # Reconnections don't need a slot or dedup check - they only replay cached events
    if is_reconnection:
        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        fly_alloc_id = os.environ.get("FLY_ALLOC_ID")
        if fly_alloc_id:
            headers["fly-replay-src"] = fly_alloc_id

        return StreamingResponse(
            _stream_generator(
                ticker_list,
                request,
                last_event_id=last_event_id,
                resume_run_id=resume_run_id,
                flight_key=None,
            ),
            media_type="text/event-stream",
            headers=headers,
        )

    # Acquire concurrency slot (new analyses only)
    slot_acquired = await acquire_analysis_slot()
    if not slot_acquired:
        return JSONResponse(
            status_code=503,
            content={"error": "Server at capacity, please retry in a few seconds"},
            headers={"Retry-After": "5"},
        )

    # Singleflight: reject duplicate concurrent requests for the same ticker set.
    # Prevents burning rate-limit budget on parallel LLM pipelines for identical work.
    flight_key = "|".join(sorted(ticker_list))
    if flight_key in _in_flight_tickers:
        release_analysis_slot()
        return JSONResponse(
            status_code=202,
            content={
                "status": "in_progress",
                "message": f"Analysis already in progress for {', '.join(ticker_list)}",
                "retry_after": 30,
            },
            headers={"Retry-After": "30"},
        )
    # Claim immediately (no await between check and add = atomic in asyncio)
    _in_flight_tickers.add(flight_key)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    # Fly.io: pin SSE reconnections to this machine (holds in-memory event store)
    fly_alloc_id = os.environ.get("FLY_ALLOC_ID")
    if fly_alloc_id:
        headers["fly-replay-src"] = fly_alloc_id

    return StreamingResponse(
        _stream_generator(
            ticker_list,
            request,
            last_event_id=None,
            resume_run_id=None,
            flight_key=flight_key,
        ),
        media_type="text/event-stream",
        headers=headers,
    )
