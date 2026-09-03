"""
Chaos injection tests.

Simulate infrastructure failures and verify graceful degradation.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _mock_astream_events_with_exception(exception_cls, exception_msg="simulated failure"):
    """Generate stream events where the agent raises an exception."""

    async def _fake_stream(*args, **kwargs):
        events = [
            {"event": "on_chain_start", "name": "router", "data": {}},
            {"event": "on_chain_start", "name": "fetch_data", "data": {}},
        ]
        for e in events:
            yield e
        raise exception_cls(exception_msg)

    return _fake_stream


def _mock_astream_events_normal():
    """Generate a normal stream of events that completes successfully."""

    async def _fake_stream(*args, **kwargs):
        events = [
            {"event": "on_chain_start", "name": "router", "data": {}},
            {"event": "on_chain_start", "name": "fetch_data", "data": {}},
            {
                "event": "on_tool_start",
                "name": "get_quote",
                "data": {"input": {"ticker": "AAPL"}},
            },
            {
                "event": "on_tool_end",
                "name": "get_quote",
                "data": {"output": {"price": 195.0}},
            },
            {"event": "on_chain_start", "name": "debate", "data": {}},
            {"event": "on_chain_start", "name": "generate_report", "data": {}},
        ]
        for e in events:
            yield e

    return _fake_stream


def _mock_astream_events_slow():
    """Generate events that take longer than the timeout."""

    async def _fake_stream(*args, **kwargs):
        yield {"event": "on_chain_start", "name": "router", "data": {}}
        # Simulate stuck tool call (exceeds the 2s timeout patched in test)
        await asyncio.sleep(10)
        yield {"event": "on_chain_start", "name": "fetch_data", "data": {}}

    return _fake_stream


def _setup_standard_mocks(mock_build_graph, mock_checkpointer, stream_factory=None):
    """Set up standard mocks for the agent pipeline."""
    # Graph
    mock_compiled = MagicMock()
    if stream_factory:
        mock_compiled.astream_events = stream_factory()
    else:
        mock_compiled.astream_events = _mock_astream_events_normal()

    mock_state = MagicMock()
    mock_state.values = {"ticker_analyses": {}}
    mock_compiled.aget_state = AsyncMock(return_value=mock_state)

    mock_graph = MagicMock()
    mock_graph.compile.return_value = mock_compiled
    mock_build_graph.return_value = mock_graph

    # get_checkpointer is an async context manager
    mock_cp_instance = MagicMock()
    mock_checkpointer.return_value.__aenter__ = AsyncMock(return_value=mock_cp_instance)
    mock_checkpointer.return_value.__aexit__ = AsyncMock(return_value=False)

    return mock_compiled


def _make_patches():
    """Create fresh patch objects to isolate infrastructure singletons."""
    mock_coordinator = MagicMock(
        is_draining=False,
        register=MagicMock(),
        drain=AsyncMock(),
        active_count=0,
        _active_streams=set(),
    )
    return [
        patch("src.api.shutdown.shutdown_coordinator", mock_coordinator),
        patch("src.api.routes.analyze_stream.shutdown_coordinator", mock_coordinator),
        patch(
            "src.api.routes.analyze_stream.acquire_analysis_slot",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("src.api.routes.analyze_stream.release_analysis_slot"),
        patch("src.db.get_pool", new_callable=AsyncMock),
        patch("src.db.init_schema", new_callable=AsyncMock),
        patch("src.db.close_pool", new_callable=AsyncMock),
        patch("src.agent.direct_tools.load_direct_tools", return_value={}),
    ]


@pytest.fixture
def client():
    """Create a test client with infrastructure singletons mocked."""
    patches = _make_patches()
    for p in patches:
        p.start()

    try:
        from src.api.main import app

        with TestClient(app) as c:
            yield c
    finally:
        for p in reversed(patches):
            p.stop()


def _parse_sse_events(response) -> list[dict]:
    """Extract parsed JSON events from an SSE response."""
    events = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            try:
                event = json.loads(line[6:])
                events.append(event)
            except json.JSONDecodeError:
                continue
    return events


class TestLLMTimeoutReturnsErrorEvent:
    """Mock the LLM call to raise asyncio.TimeoutError."""

    @patch("src.api.routes.analyze_stream.EXECUTION_TIMEOUT_BASE", 1)
    @patch("src.api.routes.analyze_stream.EXECUTION_TIMEOUT_PER_TICKER", 1)
    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_llm_timeout_returns_error_event(
        self, mock_build_graph, mock_checkpointer, client
    ):
        """LLM timeout produces a structured analysis_timeout event and the
        stream terminates cleanly (not a generic unrecoverable error, since
        this signals a retryable partial outcome)."""
        _setup_standard_mocks(
            mock_build_graph,
            mock_checkpointer,
            stream_factory=_mock_astream_events_slow,
        )

        with client.stream("GET", "/api/analyze/stream?tickers=AAPL") as response:
            events = _parse_sse_events(response)

        # Should have run_started
        assert events[0]["type"] == "run_started"

        # Should have an analysis_timeout event, not a generic error
        timeout_events = [e for e in events if e["type"] == "analysis_timeout"]
        assert len(timeout_events) >= 1, "Expected analysis_timeout event for timeout"
        assert "timed out" in timeout_events[0]["payload"]["message"].lower()
        assert timeout_events[0]["payload"]["retry_after_seconds"] > 0

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 0

        # Should still end with run_completed (graceful shutdown)
        assert events[-1]["type"] == "run_completed"


class TestMCPServerCrashPopulatesDataGaps:
    """Mock an MCP tool to raise an exception during execution."""

    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_mcp_server_crash_emits_error_event(
        self, mock_build_graph, mock_checkpointer, client
    ):
        """When the agent stream raises an exception, an error event is emitted."""
        _setup_standard_mocks(
            mock_build_graph,
            mock_checkpointer,
            stream_factory=lambda: _mock_astream_events_with_exception(
                RuntimeError, "MCP server connection lost"
            ),
        )

        with client.stream("GET", "/api/analyze/stream?tickers=AAPL") as response:
            events = _parse_sse_events(response)

        # Should have run_started
        assert events[0]["type"] == "run_started"

        # Should have an error event
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) >= 1, "Expected error event for MCP crash"
        assert "MCP server" in error_events[0]["payload"]["message"]

        # Stream should still terminate with run_completed
        assert events[-1]["type"] == "run_completed"


class TestPostgresUnavailableStreamStillWorks:
    """Mock the DB persist call to raise. Stream should still complete."""

    @patch("src.middleware.cost_tracker.execute", new_callable=AsyncMock)
    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_postgres_unavailable_stream_still_works(
        self, mock_build_graph, mock_checkpointer, mock_db_execute, client
    ):
        """Persistence failure does not break the SSE stream."""
        mock_db_execute.side_effect = ConnectionRefusedError("PostgreSQL unavailable")

        _setup_standard_mocks(mock_build_graph, mock_checkpointer)

        with client.stream("GET", "/api/analyze/stream?tickers=AAPL") as response:
            events = _parse_sse_events(response)

        # Stream should complete normally despite DB failure
        assert events[0]["type"] == "run_started"
        assert events[-1]["type"] == "run_completed"

        # Should not contain an error event about PostgreSQL
        # (persistence is non-critical, handled silently)
        error_events = [e for e in events if e["type"] == "error"]
        pg_errors = [
            e for e in error_events if "PostgreSQL" in e["payload"].get("message", "")
        ]
        assert len(pg_errors) == 0, "PostgreSQL failure should not produce user-facing errors"


class TestConcurrentAnalysesComplete:
    """Launch multiple sequential analysis requests and verify they all complete."""

    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_concurrent_analyses_all_complete(
        self, mock_build_graph, mock_checkpointer, client
    ):
        """Multiple requests should all complete without crashing."""
        results = []
        for ticker in ["AAPL", "NVDA", "TSLA"]:
            # Re-setup mocks since astream_events is consumed per call
            _setup_standard_mocks(mock_build_graph, mock_checkpointer)

            with client.stream(
                "GET", f"/api/analyze/stream?tickers={ticker}"
            ) as response:
                events = _parse_sse_events(response)
                results.append(events)

        # All requests should have completed successfully
        for i, events in enumerate(results):
            assert events[0]["type"] == "run_started", f"Request {i} missing run_started"
            assert events[-1]["type"] == "run_completed", f"Request {i} missing run_completed"

    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_concurrent_requests_have_unique_run_ids(
        self, mock_build_graph, mock_checkpointer, client
    ):
        """Each request should get a unique run_id."""
        run_ids = []

        for ticker in ["AAPL", "MSFT"]:
            _setup_standard_mocks(mock_build_graph, mock_checkpointer)

            with client.stream(
                "GET", f"/api/analyze/stream?tickers={ticker}"
            ) as response:
                events = _parse_sse_events(response)
                if events:
                    run_ids.append(events[0]["run_id"])

        assert len(run_ids) == 2
        assert run_ids[0] != run_ids[1], "Each request should have a unique run_id"
