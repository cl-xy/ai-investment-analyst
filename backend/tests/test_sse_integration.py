"""
Integration test for the SSE streaming endpoint.

Verifies the event contract: correct ordering, required fields, and
that the stream completes with a run_completed event.

Uses TestClient with mocked LangGraph execution to test the SSE wire format
without requiring actual LLM calls or MCP servers.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _mock_astream_events():
    """Generate fake LangGraph stream events in correct order."""

    async def _fake_stream(*args, **kwargs):
        events = [
            {"event": "on_chain_start", "name": "router", "data": {}},
            {"event": "on_chain_start", "name": "fetch_data", "data": {}},
            {"event": "on_tool_start", "name": "get_quote", "data": {"input": {"ticker": "NVDA"}}},
            {"event": "on_tool_end", "name": "get_quote", "data": {"output": {"price": 875.0}}},
            {
                "event": "on_tool_start",
                "name": "get_ticker_news",
                "data": {"input": {"ticker": "NVDA"}},
            },
            {"event": "on_tool_end", "name": "get_ticker_news", "data": {"output": []}},
            {"event": "on_chain_start", "name": "analyze_ticker", "data": {}},
            {
                "event": "on_chat_model_stream",
                "name": "llm",
                "data": {"chunk": MagicMock(content="NVDA looks ")},
            },
            {
                "event": "on_chat_model_stream",
                "name": "llm",
                "data": {"chunk": MagicMock(content="strong")},
            },
        ]
        for e in events:
            yield e

    return _fake_stream


def _mock_compiled_graph():
    """Create a mock compiled graph with astream_events and aget_state."""
    mock_compiled = MagicMock()
    mock_compiled.astream_events = _mock_astream_events()

    # Mock final state
    mock_state = MagicMock()
    mock_state.values = {
        "ticker_analyses": {
            "NVDA": {
                "ticker": "NVDA",
                "signal": "buy",
                "confidence": "high",
                "sentiment_score": 0.75,
                "news_summary": "Strong momentum",
                "risk_flags": ["Valuation"],
                "price_data": {"price": 875.0},
                "fundamentals": {},
                "sec_notes": "",
            }
        }
    }
    mock_compiled.aget_state = AsyncMock(return_value=mock_state)
    return mock_compiled


@pytest.fixture
def client():
    """Create a test client with mocked DB pool."""
    with patch("src.db.get_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        with patch("src.db.init_schema", new_callable=AsyncMock):
            from src.api.main import app

            with TestClient(app) as c:
                yield c


class TestSSEEventContract:
    """Verify the SSE wire format and event ordering."""

    @patch("src.api.routes.analyze_stream.acquire_analysis_slot", new_callable=AsyncMock, return_value=True)
    @patch("src.api.routes.analyze_stream.get_checkpointer")
    @patch("src.api.routes.analyze_stream.build_graph")
    def test_stream_emits_events_in_order(self, mock_build_graph, mock_checkpointer, mock_slot, client):
        """The stream should emit run_started first and run_completed last."""
        # Setup mocks
        mock_compiled = _mock_compiled_graph()
        mock_graph = MagicMock()
        mock_graph.compile.return_value = mock_compiled
        mock_build_graph.return_value = mock_graph

        # get_checkpointer is an async context manager
        mock_cp = AsyncMock()
        mock_cp.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.__aexit__ = AsyncMock(return_value=False)
        mock_checkpointer.return_value = mock_cp

        # Provide tool_map on app state (normally set at startup)
        client.app.state.mcp_tools = {}

        # Make the stream
        with client.stream("GET", "/api/analyze/stream?tickers=NVDA") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            events = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        events.append(event)
                    except json.JSONDecodeError:
                        continue

        # Verify we got events
        assert len(events) > 0

        # First event must be run_started
        assert events[0]["type"] == "run_started"
        assert events[0]["payload"]["tickers"] == ["NVDA"]

        # Last event must be run_completed
        assert events[-1]["type"] == "run_completed"
        assert "total_duration_ms" in events[-1]["payload"]

        # All events have required envelope fields
        for event in events:
            assert "run_id" in event
            assert "seq" in event
            assert "type" in event
            assert "timestamp" in event
            assert isinstance(event["seq"], int)

        # Sequence IDs are monotonically increasing
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)  # No duplicates

    def test_stream_validates_input(self, client):
        """Invalid tickers should return error JSON, not start streaming."""
        response = client.get("/api/analyze/stream?tickers=INVALID!!!")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Invalid ticker" in data["detail"]

    def test_stream_rejects_too_many_tickers(self, client):
        """More than 3 tickers should be rejected."""
        response = client.get("/api/analyze/stream?tickers=A,B,C,D,E,F")
        assert response.status_code == 400
        data = response.json()
        assert "Maximum 3" in data["detail"]

    def test_stream_headers(self, client):
        """SSE responses need correct headers to prevent buffering."""

        async def _empty_generator(*args, **kwargs):
            yield "data: {}\n\n"

        with (
            patch(
                "src.api.routes.analyze_stream.acquire_analysis_slot",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.api.routes.analyze_stream._stream_generator",
                side_effect=_empty_generator,
            ),
        ):
            response = client.get("/api/analyze/stream?tickers=NVDA")

        assert response.headers.get("cache-control") == "no-cache"
        assert response.headers.get("x-accel-buffering") == "no"


class TestSSEEventPayloads:
    """Verify individual event type payloads match the contract."""

    def test_run_started_contains_tickers(self):
        """run_started payload must include the tickers array."""
        from src.agent.events import EventEmitter

        emitter = EventEmitter()
        event = emitter.run_started(["NVDA", "AAPL"])
        assert event.payload["tickers"] == ["NVDA", "AAPL"]

    def test_node_completed_contains_duration(self):
        """node_completed payload must include duration_ms."""
        import time

        from src.agent.events import EventEmitter

        emitter = EventEmitter()
        emitter.node_started("router")
        time.sleep(0.01)
        event = emitter.node_completed("router")
        assert event.payload["duration_ms"] >= 10
        assert event.payload["node_name"] == "router"

    def test_tool_result_contains_all_fields(self):
        """tool_result must have success, cached, duration_ms, source_id."""
        from src.agent.events import EventEmitter

        emitter = EventEmitter()
        event = emitter.tool_result(
            "get_quote",
            success=True,
            cached=True,
            duration_ms=42,
            source_id="yfinance:NVDA:123",
            node="fetch_data",
        )
        payload = event.payload
        assert payload["success"] is True
        assert payload["cached"] is True
        assert payload["duration_ms"] == 42
        assert payload["source_id"] == "yfinance:NVDA:123"
        assert event.node == "fetch_data"
        assert event.tool == "get_quote"

    def test_run_completed_contains_metrics(self):
        """run_completed must include total_duration_ms, total_tokens, cost_usd."""
        from src.agent.events import EventEmitter

        emitter = EventEmitter()
        event = emitter.run_completed(
            ["NVDA"], total_duration_ms=8500, total_tokens=3200, cost_usd=0.0025
        )
        assert event.payload["total_duration_ms"] == 8500
        assert event.payload["total_tokens"] == 3200
        assert event.payload["cost_usd"] == 0.0025
