"""
Tests for the SSE event schema and emitter.
Verifies the domain event contract between backend and frontend.
"""

import json

import pytest

from src.agent.events import EventEmitter, EventType, StreamEvent


class TestStreamEvent:
    def test_to_sse_format(self):
        event = StreamEvent(
            run_id="test-123",
            seq=1,
            type=EventType.RUN_STARTED,
            timestamp="2024-01-01T00:00:00Z",
            payload={"tickers": ["NVDA"]},
        )
        sse = event.to_sse()
        assert sse.startswith("id: 1\n")
        assert "event: run_started\n" in sse
        assert "data: " in sse
        # Should end with double newline
        assert sse.endswith("\n\n")

    def test_sse_data_is_valid_json(self):
        event = StreamEvent(
            run_id="test-123",
            seq=5,
            type=EventType.TOOL_RESULT,
            timestamp="2024-01-01T00:00:00Z",
            node="fetch_data",
            tool="get_quote",
            payload={"tool_name": "get_quote", "success": True, "cached": True, "duration_ms": 42},
        )
        sse = event.to_sse()
        data_line = [l for l in sse.split("\n") if l.startswith("data: ")][0]
        data_json = data_line.removeprefix("data: ")
        parsed = json.loads(data_json)
        assert parsed["run_id"] == "test-123"
        assert parsed["seq"] == 5
        assert parsed["type"] == "tool_result"
        assert parsed["payload"]["cached"] is True


class TestEventEmitter:
    def test_monotonic_sequence(self):
        emitter = EventEmitter(run_id="test-run")
        e1 = emitter.run_started(["NVDA"])
        e2 = emitter.node_started("router")
        e3 = emitter.node_completed("router")

        assert e1.seq == 1
        assert e2.seq == 2
        assert e3.seq == 3

    def test_run_started_payload(self):
        emitter = EventEmitter()
        event = emitter.run_started(["NVDA", "AAPL"])
        assert event.type == EventType.RUN_STARTED
        assert event.payload == {"tickers": ["NVDA", "AAPL"]}

    def test_node_lifecycle_tracks_duration(self):
        import time

        emitter = EventEmitter()
        emitter.node_started("fetch_data")
        time.sleep(0.01)  # Small delay
        completed = emitter.node_completed("fetch_data")
        assert completed.payload["duration_ms"] >= 10
        assert completed.payload["node_name"] == "fetch_data"

    def test_tool_result_fields(self):
        emitter = EventEmitter()
        event = emitter.tool_result(
            "get_quote",
            success=True,
            cached=True,
            duration_ms=45,
            source_id="yfinance:NVDA:1706140800",
            node="fetch_data",
        )
        assert event.type == EventType.TOOL_RESULT
        assert event.node == "fetch_data"
        assert event.tool == "get_quote"
        assert event.payload["cached"] is True
        assert event.payload["source_id"] == "yfinance:NVDA:1706140800"

    def test_error_event(self):
        emitter = EventEmitter()
        event = emitter.error("Connection timeout", recoverable=False, context="groq_api")
        assert event.type == EventType.ERROR
        assert event.payload["recoverable"] is False
        assert event.payload["context"] == "groq_api"

    def test_analysis_complete(self):
        emitter = EventEmitter()
        analysis = {"ticker": "NVDA", "signal": "buy", "confidence": "high"}
        event = emitter.analysis_complete("NVDA", analysis)
        assert event.type == EventType.ANALYSIS_COMPLETE
        assert event.payload["ticker"] == "NVDA"
        assert event.payload["analysis"]["signal"] == "buy"

    def test_heartbeat(self):
        emitter = EventEmitter()
        event = emitter.heartbeat()
        assert event.type == EventType.HEARTBEAT
        assert event.payload == {}

    def test_events_list_accumulates(self):
        emitter = EventEmitter()
        emitter.run_started(["NVDA"])
        emitter.node_started("router")
        emitter.heartbeat()
        assert len(emitter.events) == 3

    def test_run_id_auto_generated(self):
        emitter = EventEmitter()
        assert len(emitter.run_id) > 0
        # Should be UUID format
        assert "-" in emitter.run_id
