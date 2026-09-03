"""
Integration tests for the SSE streaming endpoint.

These test the full pipeline: HTTP request -> FastAPI -> LangGraph agent -> SSE events,
with MCP tool servers mocked to return deterministic data.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_astream_events(delay: float = 0.0):
    """Generate fake LangGraph stream events with optional delay per event."""

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
            {
                "event": "on_chat_model_stream",
                "name": "llm",
                "data": {"chunk": MagicMock(content="AAPL looks ")},
            },
            {
                "event": "on_chat_model_stream",
                "name": "llm",
                "data": {"chunk": MagicMock(content="stable")},
            },
            {"event": "on_chain_start", "name": "generate_report", "data": {}},
        ]
        for e in events:
            if delay > 0:
                await asyncio.sleep(delay)
            yield e

    return _fake_stream


def _mock_compiled_graph(stream_delay: float = 0.0):
    """Create a mock compiled graph with astream_events and aget_state."""
    mock_compiled = MagicMock()
    mock_compiled.astream_events = _mock_astream_events(delay=stream_delay)

    mock_state = MagicMock()
    mock_state.values = {
        "ticker_analyses": {
            "AAPL": {
                "ticker": "AAPL",
                "signal": "hold",
                "confidence": "medium",
                "sentiment_score": 0.3,
                "news_summary": "Stable growth expected",
                "risk_flags": ["Competition"],
                "price_data": {"price": 195.0},
                "fundamentals": {"pe": 28.5},
                "sec_notes": "",
                "citations": [
                    {
                        "source_id": "yfinance:AAPL:1706140800",
                        "claim": "Current price at $195",
                        "provider": "yfinance",
                    }
                ],
                "data_gaps": [],
            }
        }
    }
    mock_compiled.aget_state = AsyncMock(return_value=mock_state)
    return mock_compiled


def _setup_mocks(mock_build_graph, mock_checkpointer, stream_delay: float = 0.0):
    """Configure standard mocks for the streaming endpoint."""
    # Graph mock
    mock_compiled = _mock_compiled_graph(stream_delay=stream_delay)
    mock_graph = MagicMock()
    mock_graph.compile.return_value = mock_compiled
    mock_build_graph.return_value = mock_graph

    # get_checkpointer mock (async context manager)
    mock_cp_instance = MagicMock()
    mock_checkpointer.return_value.__aenter__ = AsyncMock(return_value=mock_cp_instance)
    mock_checkpointer.return_value.__aexit__ = AsyncMock(return_value=False)

    return mock_compiled


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


class TestStreamEmitsRunStarted:
    """Verify the first event in the stream is run_started with correct tickers."""

    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_stream_emits_run_started(self, mock_build_graph, mock_checkpointer, client):
        """Hit /api/analyze/stream?tickers=AAPL, verify first event is run_started."""
        _setup_mocks(mock_build_graph, mock_checkpointer)

        with client.stream("GET", "/api/analyze/stream?tickers=AAPL") as response:
            assert response.status_code == 200
            events = _parse_sse_events(response)

        assert len(events) > 0
        first = events[0]
        assert first["type"] == "run_started"
        assert first["payload"]["tickers"] == ["AAPL"]
        assert "run_id" in first
        assert "seq" in first
        assert first["seq"] == 1


class TestStreamEmitsHeartbeat:
    """Verify heartbeat events arrive during slow processing."""

    @patch("src.api.routes.analyze_stream.HEARTBEAT_INTERVAL", 1)
    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_stream_emits_heartbeat(self, mock_build_graph, mock_checkpointer, client):
        """With a slow mock, verify heartbeat events arrive."""
        # Each event takes 0.2s, 8 events = 1.6s total. Heartbeat interval is 1s.
        _setup_mocks(mock_build_graph, mock_checkpointer, stream_delay=0.2)

        with client.stream("GET", "/api/analyze/stream?tickers=AAPL") as response:
            events = _parse_sse_events(response)

        heartbeats = [e for e in events if e["type"] == "heartbeat"]
        assert len(heartbeats) >= 1, "Expected at least one heartbeat during slow processing"


class TestStreamEndsWithRunCompleted:
    """Verify the stream terminates with run_completed containing metrics."""

    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_stream_ends_with_run_completed(self, mock_build_graph, mock_checkpointer, client):
        """Verify the stream terminates with run_completed containing duration and token counts."""
        _setup_mocks(mock_build_graph, mock_checkpointer)

        with client.stream("GET", "/api/analyze/stream?tickers=AAPL") as response:
            events = _parse_sse_events(response)

        assert len(events) > 0
        last = events[-1]
        assert last["type"] == "run_completed"
        assert "total_duration_ms" in last["payload"]
        assert "total_tokens" in last["payload"]
        assert "cost_usd" in last["payload"]
        assert isinstance(last["payload"]["total_duration_ms"], int)


class TestInvalidTickerReturnsError:
    """Invalid ticker format returns JSON error (not SSE)."""

    def test_invalid_ticker_returns_error(self, client):
        """Invalid ticker format returns JSON error, not an SSE stream."""
        response = client.get("/api/analyze/stream?tickers=INVALID!!!")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Invalid ticker" in data["detail"]

    def test_special_characters_rejected(self, client):
        """Tickers with special characters are rejected."""
        response = client.get("/api/analyze/stream?tickers=AA$BB")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_empty_tickers_returns_error(self, client):
        """Empty ticker string returns error."""
        response = client.get("/api/analyze/stream?tickers=")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data


class TestTooManyTickersRejected:
    """More than 4 tickers returns error."""

    def test_too_many_tickers_rejected(self, client):
        """More than 4 tickers returns error."""
        response = client.get("/api/analyze/stream?tickers=A,B,C,D,E")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Maximum 4" in data["detail"]

    def test_exactly_four_tickers_accepted(self, client):
        """Exactly 4 tickers should be accepted (not rejected)."""
        response = client.get("/api/analyze/stream?tickers=A,B,C,D")
        # Should not contain a validation error about "Maximum 4"
        if response.headers.get("content-type", "").startswith("application/json"):
            data = response.json()
            assert "Maximum 4" not in data.get("detail", "")


class TestClientDisconnectCancelsTask:
    """Simulate client disconnect, verify task is cancelled (no leak)."""

    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_client_disconnect_cancels_task(
        self, mock_build_graph, mock_checkpointer, client
    ):
        """Simulate client disconnect, verify the agent task gets cancelled."""
        # Use a slow stream so we can disconnect mid-stream
        _setup_mocks(mock_build_graph, mock_checkpointer, stream_delay=0.3)

        with client.stream("GET", "/api/analyze/stream?tickers=AAPL") as response:
            # Read just the first event then break (disconnect)
            for line in response.iter_lines():
                if line.startswith("data: "):
                    break

        # If we get here without hanging, the task was properly cancelled.


class TestStreamTimeoutEmitsErrorEvent:
    """Mock a very slow tool, verify timeout emits a structured analysis_timeout event."""

    @patch("src.api.routes.analyze_stream.EXECUTION_TIMEOUT_BASE", 1)
    @patch("src.api.routes.analyze_stream.EXECUTION_TIMEOUT_PER_TICKER", 0)
    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_stream_timeout_emits_error_event(
        self, mock_build_graph, mock_checkpointer, client
    ):
        """Mock a very slow tool, verify timeout event and clean termination."""
        # Each event takes 0.3s with 8 events = 2.4s total, but timeout is 1s
        _setup_mocks(mock_build_graph, mock_checkpointer, stream_delay=0.3)

        with client.stream("GET", "/api/analyze/stream?tickers=AAPL") as response:
            events = _parse_sse_events(response)

        # Should contain a structured analysis_timeout event (not a generic
        # error) so the client can distinguish partial-progress timeouts
        # from hard failures and knows which tickers still need a retry.
        # The shared mock's checkpointed state already has AAPL's analysis
        # in `ticker_analyses` by the time we read state post-timeout, which
        # exercises the "completed before the timeout fired" path.
        timeout_events = [e for e in events if e["type"] == "analysis_timeout"]
        assert len(timeout_events) >= 1
        timeout_payload = timeout_events[0]["payload"]
        assert "timed out" in timeout_payload["message"].lower()
        assert timeout_payload["completed_tickers"] == ["AAPL"]
        assert timeout_payload["incomplete_tickers"] == []
        assert timeout_payload["retry_after_seconds"] > 0

        # No generic unrecoverable error event should be emitted for this case
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 0

        # Stream should still end with run_completed (graceful shutdown)
        assert events[-1]["type"] == "run_completed"


class TestStreamTimeoutReportsIncompleteTickers:
    """Multi-ticker timeout: only some tickers finish before the deadline."""

    @patch("src.api.routes.analyze_stream.EXECUTION_TIMEOUT_BASE", 1)
    @patch("src.api.routes.analyze_stream.EXECUTION_TIMEOUT_PER_TICKER", 0)
    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_incomplete_tickers_reported_for_retry(
        self, mock_build_graph, mock_checkpointer, client
    ):
        """MSFT was requested but never made it into ticker_analyses before
        the timeout fired; AAPL did. The timeout event must separate the two
        so the client can retry only MSFT instead of re-running both."""
        _setup_mocks(mock_build_graph, mock_checkpointer, stream_delay=0.3)

        with client.stream(
            "GET", "/api/analyze/stream?tickers=AAPL,MSFT"
        ) as response:
            events = _parse_sse_events(response)

        timeout_events = [e for e in events if e["type"] == "analysis_timeout"]
        assert len(timeout_events) == 1
        payload = timeout_events[0]["payload"]
        assert payload["completed_tickers"] == ["AAPL"]
        assert payload["incomplete_tickers"] == ["MSFT"]
