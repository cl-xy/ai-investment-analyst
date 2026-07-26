"""
SSE streaming endpoint for real-time analysis with agent trace.

Maps LangGraph execution events to domain-specific SSE events, providing
full observability into the agent pipeline: tool calls, cache hits, LLM
streaming, and progressive analysis delivery.
"""

import asyncio
import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.agent.events import EventEmitter
from src.agent.graph import build_graph
from src.agent.mcp_client import create_mcp_client

router = APIRouter()

HEARTBEAT_INTERVAL = 15  # seconds


async def _heartbeat(emitter: EventEmitter, queue: asyncio.Queue, stop: asyncio.Event):
    """Send periodic heartbeats to keep the SSE connection alive."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL)
            break
        except asyncio.TimeoutError:
            event = emitter.heartbeat()
            await queue.put(event.to_sse())


async def _run_agent(tickers: list[str], emitter: EventEmitter, queue: asyncio.Queue):
    """Execute the LangGraph agent and emit domain events to the queue."""
    start_time = time.monotonic()
    tickers_upper = [t.upper() for t in tickers]

    # Emit run_started
    event = emitter.run_started(tickers_upper)
    await queue.put(event.to_sse())

    try:
        Path("data").mkdir(exist_ok=True)
        message = f"Analyze these stocks: {', '.join(tickers_upper)}"

        client = create_mcp_client()
        tools_list = await client.get_tools()
        mcp_tools = {t.name: t for t in tools_list}
        graph = build_graph(mcp_tools)

        async with AsyncSqliteSaver.from_conn_string("data/checkpointer.db") as checkpointer:
            compiled = graph.compile(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": f"stream-{emitter.run_id}"}}
            initial_state = {
                "messages": [HumanMessage(content=message)],
                "tickers_to_analyze": tickers_upper,
            }

            current_node = None

            async for event_data in compiled.astream_events(
                initial_state, config=config, version="v2"
            ):
                kind = event_data.get("event")
                name = event_data.get("name", "")
                data = event_data.get("data", {})

                # Node lifecycle events
                if kind == "on_chain_start" and name in (
                    "router", "fetch_data", "analyze_ticker", "generate_report",
                    "chat", "portfolio_ops",
                ):
                    if current_node:
                        ev = emitter.node_completed(current_node)
                        await queue.put(ev.to_sse())
                    current_node = name
                    ev = emitter.node_started(name)
                    await queue.put(ev.to_sse())

                # Tool invocation events
                elif kind == "on_tool_start":
                    tool_name = name
                    tool_input = data.get("input", {})
                    ev = emitter.tool_call(tool_name, tool_input, node=current_node)
                    await queue.put(ev.to_sse())

                elif kind == "on_tool_end":
                    tool_name = name
                    output = data.get("output", "")
                    success = "error" not in str(output).lower()[:100]
                    ev = emitter.tool_result(
                        tool_name, success=success, cached=False,
                        duration_ms=0, source_id=f"{tool_name}:{int(time.time())}",
                        node=current_node,
                    )
                    await queue.put(ev.to_sse())

                # LLM token streaming
                elif kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        ev = emitter.llm_token(chunk.content, node=current_node)
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

    except Exception as exc:
        ev = emitter.error(str(exc), recoverable=False, context="agent_execution")
        await queue.put(ev.to_sse())

    # Run completed
    total_ms = int((time.monotonic() - start_time) * 1000)
    ev = emitter.run_completed(tickers_upper, total_ms)
    await queue.put(ev.to_sse())

    # Signal done
    await queue.put(None)


async def _stream_generator(
    tickers: list[str], request: Request, last_event_id: int = 0,
):
    """Async generator that yields SSE events."""
    emitter = EventEmitter()
    queue: asyncio.Queue = asyncio.Queue()
    stop_heartbeat = asyncio.Event()

    # Start the agent and heartbeat tasks
    agent_task = asyncio.create_task(_run_agent(tickers, emitter, queue))
    heartbeat_task = asyncio.create_task(_heartbeat(emitter, queue, stop_heartbeat))

    try:
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                msg = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if msg is None:
                break

            yield msg

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


@router.get("/analyze/stream")
async def analyze_stream(
    request: Request,
    tickers: str = Query(..., description="Comma-separated ticker symbols"),
):
    """
    SSE endpoint for streaming analysis with full agent trace.

    Sends domain-specific events: run_started, node_started, node_completed,
    tool_call, tool_result, llm_token, analysis_complete, run_completed.
    Heartbeats every 15s to prevent proxy timeouts.
    """
    import re

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return {"error": "At least one ticker is required"}

    # Validate ticker format: alphanumeric + dots, max 10 chars each
    valid_pattern = re.compile(r"^[A-Z0-9.]{1,10}$")
    invalid = [t for t in ticker_list if not valid_pattern.match(t)]
    if invalid:
        return {"error": f"Invalid ticker symbols: {', '.join(invalid)}"}

    # Cap at 5 tickers per request
    if len(ticker_list) > 5:
        return {"error": "Maximum 5 tickers per analysis request"}

    # Check for reconnection
    last_event_id = 0
    if request.headers.get("Last-Event-ID"):
        try:
            last_event_id = int(request.headers["Last-Event-ID"])
        except ValueError:
            pass

    return StreamingResponse(
        _stream_generator(ticker_list, request, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
