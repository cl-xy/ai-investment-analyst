"""Tests confirming the summary NameError fix in analyze_stream._run_agent."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class FakeEmitter:
    """Minimal EventEmitter stand-in for testing _run_agent control flow."""

    def __init__(self):
        self.run_id = "test-run-123"
        self.events = []

    def _make_event(self, type_name, **kwargs):
        ev = MagicMock()
        ev.to_sse.return_value = f"event: {type_name}\ndata: {{}}\n\n"
        self.events.append(type_name)
        return ev

    def run_started(self, tickers):
        return self._make_event("run_started")

    def node_started(self, name):
        return self._make_event("node_started")

    def node_completed(self, name):
        return self._make_event("node_completed")

    def tool_call(self, name, args, node=None):
        return self._make_event("tool_call")

    def tool_result(self, name, **kwargs):
        return self._make_event("tool_result")

    def llm_token(self, text, node=None):
        return self._make_event("llm_token")

    def analysis_complete(self, ticker, analysis):
        return self._make_event("analysis_complete")

    def run_completed(self, tickers, total_duration_ms, total_tokens=0, cost_usd=0.0):
        return self._make_event("run_completed")

    def error(self, message, recoverable=True, context=""):
        return self._make_event("error")

    def heartbeat(self):
        return self._make_event("heartbeat")


class FakeTracker:
    """Minimal CostTracker stand-in."""

    def __init__(self):
        self._start = time.monotonic()

    def record_tool_call(self, success, cached):
        pass

    def record_tokens(self, prompt, completion):
        pass

    def record_schema_result(self, valid, citations, data_gaps):
        pass

    def summary(self):
        return {
            "total_duration_ms": int((time.monotonic() - self._start) * 1000),
            "total_tokens": 100,
            "cost_usd": 0.001,
            "tool_calls": 5,
            "cache_hits": 2,
        }

    async def persist(self):
        pass


@pytest.mark.asyncio
async def test_run_agent_success_does_not_raise_name_error():
    """Regression test: summary must be defined before the else block uses it.

    Before the fix, the else block (success path) referenced `summary` which was
    only assigned AFTER the try/except/else, causing NameError on every success.
    """
    from src.api.routes.analyze_stream import _run_agent

    emitter = FakeEmitter()
    queue = asyncio.Queue()
    tracker = FakeTracker()

    # Mock the graph execution to succeed immediately
    fake_state = MagicMock()
    fake_state.values = {"ticker_analyses": {"NVDA": {"signal": "buy", "confidence": "high"}}}

    fake_compiled = MagicMock()

    async def fake_stream(*args, **kwargs):
        # Yield one node start event
        yield {"event": "on_chain_start", "name": "router", "data": {}}
        yield {"event": "on_chain_start", "name": "fetch_data", "data": {}}

    fake_compiled.astream_events = fake_stream
    fake_compiled.aget_state = AsyncMock(return_value=fake_state)

    fake_graph = MagicMock()
    fake_graph.compile.return_value = fake_compiled

    with (
        patch("src.api.routes.analyze_stream.build_graph", return_value=fake_graph),
        patch("src.api.routes.analyze_stream.get_checkpointer") as mock_cp,
        patch("src.api.routes.analyze_stream.metrics"),
    ):
        # Make get_checkpointer an async context manager
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=False)

        await _run_agent(["NVDA"], emitter, queue, tracker, {})

    # Drain the queue and check for run_completed event
    events = []
    while not queue.empty():
        msg = queue.get_nowait()
        if msg is not None:
            events.append(msg)

    # The run_completed event should have been emitted (not crashed by NameError)
    assert any("run_completed" in str(e) for e in events), (
        f"run_completed event not found in: {events}"
    )


@pytest.mark.asyncio
async def test_run_agent_error_path_still_emits_run_completed():
    """When the agent raises, we still emit run_completed (with error) and don't crash."""
    from src.api.routes.analyze_stream import _run_agent

    emitter = FakeEmitter()
    queue = asyncio.Queue()
    tracker = FakeTracker()

    with (
        patch("src.api.routes.analyze_stream.build_graph", side_effect=RuntimeError("LLM down")),
        patch("src.api.routes.analyze_stream.get_checkpointer") as mock_cp,
        patch("src.api.routes.analyze_stream.metrics"),
    ):
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=False)

        await _run_agent(["NVDA"], emitter, queue, tracker, {})

    events = []
    while not queue.empty():
        msg = queue.get_nowait()
        if msg is not None:
            events.append(msg)

    # Should have error AND run_completed events
    assert any("error" in str(e) for e in events)
    assert any("run_completed" in str(e) for e in events)


@pytest.mark.asyncio
async def test_run_agent_always_sends_none_sentinel():
    """The None sentinel must always be sent so _stream_generator exits cleanly.

    Even if tracker.summary() or emitter.run_completed() raises, the finally block
    must ensure queue.put(None) fires. Without this, the SSE stream hangs until
    the client disconnects.
    """
    from src.api.routes.analyze_stream import _run_agent

    emitter = FakeEmitter()
    queue = asyncio.Queue()

    # Create a tracker whose summary() raises
    class BrokenTracker(FakeTracker):
        def summary(self):
            raise RuntimeError("Tracker corrupted")

    tracker = BrokenTracker()

    with (
        patch("src.api.routes.analyze_stream.build_graph", side_effect=RuntimeError("fail")),
        patch("src.api.routes.analyze_stream.get_checkpointer") as mock_cp,
        patch("src.api.routes.analyze_stream.metrics"),
    ):
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=False)

        await _run_agent(["NVDA"], emitter, queue, tracker, {})

    # Drain queue and verify None sentinel was sent
    messages = []
    none_found = False
    while not queue.empty():
        msg = queue.get_nowait()
        if msg is None:
            none_found = True
        else:
            messages.append(msg)

    assert none_found, "None sentinel was never sent — stream would hang"
