"""Cross-machine SSE reconnection recovery.

The in-memory event store (_recent_runs) is process-local. When a reconnect
lands on a different machine, or after a rolling deploy wiped the owning
process, the serving process has no record of the run. These tests cover the
two recovery paths:

1. A completed run is replayed from the durable Postgres trace.
2. A run with no durable trace yet yields a *recoverable* error (not a hard
   dead-end), so the client retries cleanly.
"""

import json

import pytest

from src.api.routes import analyze_stream


def _parse_sse(chunk: str) -> dict:
    """Extract the JSON data payload from an SSE message block."""
    for line in chunk.split("\n"):
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    return {}


async def _drain(gen) -> list[str]:
    out = []
    async for chunk in gen:
        out.append(chunk)
    return out


@pytest.mark.asyncio
async def test_reconnect_replays_completed_run_from_postgres(monkeypatch):
    """A reconnect to a machine without in-memory state replays the DB trace."""
    monkeypatch.setattr(analyze_stream, "_recent_runs", {})

    stored_events = [
        {
            "run_id": "run-x",
            "seq": 1,
            "type": "run_started",
            "timestamp": "2026-01-01T00:00:00Z",
            "payload": {"tickers": ["OLLI"]},
        },
        {
            "run_id": "run-x",
            "seq": 2,
            "type": "node_started",
            "timestamp": "2026-01-01T00:00:01Z",
            "node": "router",
            "payload": {},
        },
        {
            "run_id": "run-x",
            "seq": 3,
            "type": "run_completed",
            "timestamp": "2026-01-01T00:00:02Z",
            "payload": {"total_duration_ms": 2000},
        },
    ]

    async def _fake_trace(run_id):
        assert run_id == "run-x"
        return {"run_id": run_id, "events": stored_events}

    monkeypatch.setattr("src.ops.trace_recorder.get_trace_by_run_id", _fake_trace)

    gen = analyze_stream._stream_generator(
        ["OLLI"], request=None, last_event_id=1, resume_run_id="run-x"
    )
    chunks = await _drain(gen)

    payloads = [_parse_sse(c) for c in chunks if "data: " in c]
    seqs = [p.get("seq") for p in payloads]
    types = [p.get("type") for p in payloads]

    # seq=1 already seen by client (last_event_id=1); only 2 and 3 replayed.
    assert seqs == [2, 3]
    assert "run_completed" in types
    # No "Run state unavailable" dead-end.
    assert all("unavailable" not in (p.get("payload", {}).get("message", "")) for p in payloads)


@pytest.mark.asyncio
async def test_reconnect_without_trace_yields_recoverable_error(monkeypatch):
    """No in-memory state and no durable trace => recoverable error, not a dead-end."""
    monkeypatch.setattr(analyze_stream, "_recent_runs", {})

    async def _no_trace(run_id):
        return None

    monkeypatch.setattr("src.ops.trace_recorder.get_trace_by_run_id", _no_trace)

    gen = analyze_stream._stream_generator(
        ["OLLI"], request=None, last_event_id=4, resume_run_id="run-missing"
    )
    chunks = await _drain(gen)

    payloads = [_parse_sse(c) for c in chunks if "data: " in c]
    assert len(payloads) == 1
    err = payloads[0]
    assert err["type"] == "error"
    assert err["payload"]["recoverable"] is True
    # Must not use the old permanent-failure wording.
    assert "start a new analysis" not in err["payload"]["message"]
