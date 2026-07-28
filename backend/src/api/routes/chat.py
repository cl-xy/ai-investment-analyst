"""
Chat endpoint. Multi-turn conversational interface with tool access via SSE.
"""

import asyncio
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage

from src.agent.checkpointer import get_checkpointer
from src.agent.events import EventEmitter
from src.agent.graph import build_graph
from src.api.shutdown import shutdown_coordinator
from src.middleware.auth import limiter

router = APIRouter(tags=["chat"])

CHAT_TIMEOUT = 120  # seconds


async def _chat_stream_generator(message: str, thread_id: str, request: Request):
    """Stream chat responses as SSE events."""
    emitter = EventEmitter()

    mcp_tools = request.app.state.mcp_tools
    graph = build_graph(mcp_tools)

    async with get_checkpointer() as checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "messages": [HumanMessage(content=message)],
            "intent": "conversational",
        }

        # Stream with hard timeout
        try:
            async with asyncio.timeout(CHAT_TIMEOUT):
                async for event_data in compiled.astream_events(
                    initial_state, config=config, version="v2"
                ):
                    if await request.is_disconnected():
                        break

                    kind = event_data.get("event")
                    data = event_data.get("data", {})

                    if kind == "on_chat_model_stream":
                        chunk = data.get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            ev = emitter.llm_token(chunk.content)
                            yield ev.to_sse()

                    elif kind == "on_tool_start":
                        name = event_data.get("name", "")
                        tool_input = data.get("input", {})
                        ev = emitter.tool_call(name, tool_input)
                        yield ev.to_sse()

                    elif kind == "on_tool_end":
                        name = event_data.get("name", "")
                        ev = emitter.tool_result(
                            name, success=True, cached=False, duration_ms=0, source_id=""
                        )
                        yield ev.to_sse()
        except TimeoutError:
            ev = emitter.error("Chat stream timed out")
            yield ev.to_sse()

    # Send completion
    ev = emitter.run_completed([], total_duration_ms=0)
    yield ev.to_sse()


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

    if not message.strip():
        return JSONResponse(status_code=400, content={"error": "Message is required"})

    if len(message) > 1000:
        return JSONResponse(status_code=400, content={"error": "Message too long (max 1000 chars)"})

    return StreamingResponse(
        _chat_stream_generator(message.strip(), thread_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
