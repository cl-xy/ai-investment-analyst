"""
Chat endpoint. Multi-turn conversational interface with tool access via SSE.
"""

import asyncio
import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage

from src.agent.checkpointer import get_checkpointer
from src.agent.events import EventEmitter
from src.agent.graph import build_graph
from src.api.shutdown import shutdown_coordinator
from src.middleware.auth import limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

CHAT_TIMEOUT = 120  # seconds
HEARTBEAT_INTERVAL = 15  # seconds


async def _chat_stream_generator(message: str, thread_id: str, request: Request):
    """Stream chat responses as SSE events."""
    emitter = EventEmitter()
    completed_ok = False

    mcp_tools = request.app.state.mcp_tools
    graph = build_graph(mcp_tools)

    # Producer task: consumes astream_events and pushes to queue.
    # Sentinel values: None = clean end, Exception instance = error.
    queue: asyncio.Queue = asyncio.Queue()

    async def _producer(compiled, initial_state, config):
        try:
            async with asyncio.timeout(CHAT_TIMEOUT):
                async for event_data in compiled.astream_events(
                    initial_state, config=config, version="v2"
                ):
                    await queue.put(event_data)
        except TimeoutError:
            await queue.put(TimeoutError("Chat stream timed out"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await queue.put(exc)
        finally:
            await queue.put(None)  # sentinel: stream ended

    try:
        async with get_checkpointer() as checkpointer:
            compiled = graph.compile(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}}

            initial_state = {
                "messages": [HumanMessage(content=message)],
                "intent": "conversational",
            }

            producer_task = asyncio.create_task(_producer(compiled, initial_state, config))

            try:
                while True:
                    if await request.is_disconnected():
                        break

                    # Wait for next event or emit heartbeat on timeout
                    try:
                        item = await asyncio.wait_for(
                            queue.get(), timeout=HEARTBEAT_INTERVAL
                        )
                    except asyncio.TimeoutError:
                        yield emitter.heartbeat().to_sse()
                        continue

                    # Sentinel: clean end
                    if item is None:
                        completed_ok = True
                        break

                    # Producer reported an error
                    if isinstance(item, BaseException):
                        if isinstance(item, TimeoutError):
                            yield emitter.error(
                                "Chat stream timed out", recoverable=False
                            ).to_sse()
                        else:
                            logger.exception(
                                "Chat stream error for thread %s", thread_id, exc_info=item
                            )
                            yield emitter.error(
                                "An internal error occurred", recoverable=False
                            ).to_sse()
                        break

                    # Normal LangGraph event
                    kind = item.get("event")
                    data = item.get("data", {})

                    if kind == "on_chat_model_stream":
                        chunk = data.get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            content = chunk.content
                            # Normalize list-of-blocks to string
                            if isinstance(content, list):
                                content = "".join(
                                    block.get("text", "")
                                    if isinstance(block, dict)
                                    else str(block)
                                    for block in content
                                )
                            if content:
                                yield emitter.llm_token(content).to_sse()

                    elif kind == "on_tool_start":
                        name = item.get("name", "")
                        tool_input = data.get("input", {})
                        yield emitter.tool_call(name, tool_input).to_sse()

                    elif kind == "on_tool_end":
                        name = item.get("name", "")
                        yield emitter.tool_result(
                            name, success=True, cached=False, duration_ms=0, source_id=""
                        ).to_sse()

                    elif kind == "on_tool_error":
                        name = item.get("name", "")
                        yield emitter.tool_result(
                            name, success=False, cached=False, duration_ms=0, source_id=""
                        ).to_sse()

            finally:
                producer_task.cancel()
                try:
                    await producer_task
                except (asyncio.CancelledError, Exception):
                    pass

    except Exception as exc:
        logger.exception("Chat stream setup error for thread %s", thread_id, exc_info=exc)
        yield emitter.error("Failed to initialize chat stream", recoverable=False).to_sse()

    # Only emit completion on successful run
    if completed_ok:
        yield emitter.run_completed([], total_duration_ms=0).to_sse()


@router.get("/chat/stream")
@limiter.limit("15/minute")
async def chat_stream(
    request: Request,
    message: str = "",
    thread_id: str = "default",
):
    """
    SSE endpoint for chat with the investment analyst agent.
    Supports multi-turn conversation via thread_id.
    """
    if shutdown_coordinator.is_draining:
        return JSONResponse(
            status_code=503,
            content={"error": "Server shutting down"},
            headers={"Retry-After": "10"},
        )

    if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", thread_id):
        return JSONResponse(status_code=400, content={"error": "Invalid thread_id format"})

    # Strip before validation so checks and downstream use are consistent
    message = message.strip()

    if not message:
        return JSONResponse(status_code=400, content={"error": "Message is required"})

    if len(message) > 1000:
        return JSONResponse(status_code=400, content={"error": "Message too long (max 1000 chars)"})

    # Validate mcp_tools before starting the stream (fail with proper HTTP error)
    mcp_tools = getattr(request.app.state, "mcp_tools", None)
    if mcp_tools is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Service temporarily unavailable"},
        )

    return StreamingResponse(
        _chat_stream_generator(message, thread_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )
