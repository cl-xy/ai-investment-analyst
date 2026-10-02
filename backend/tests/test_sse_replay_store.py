"""
Regression tests for SSE replay store memory bounding.

_store_event must not retain high-frequency llm_token/heartbeat frames (the
unbounded allocation), while still retaining domain events so gapless
reconnection via Last-Event-ID keeps working across token gaps.
"""

from src.api.routes import analyze_stream as mod


def _frame(seq: int, event_type: str) -> str:
    return f"id: {seq}\nevent: {event_type}\ndata: {{}}\n\n"


def _reset_store():
    mod._recent_runs.clear()
    mod._last_eviction = 0.0


def test_llm_token_and_heartbeat_frames_not_retained():
    _reset_store()
    mod._store_event("run-1", _frame(1, "run_started"))
    mod._store_event("run-1", _frame(2, "llm_token"))
    mod._store_event("run-1", _frame(3, "heartbeat"))
    mod._store_event("run-1", _frame(4, "analysis_complete"))

    _, frames = mod._recent_runs["run-1"]
    retained_types = [next(ln for ln in f.split("\n") if ln.startswith("event: ")) for f in frames]
    assert retained_types == ["event: run_started", "event: analysis_complete"]


def test_replay_returns_domain_events_across_token_gaps():
    _reset_store()
    mod._store_event("run-2", _frame(1, "run_started"))
    mod._store_event("run-2", _frame(2, "llm_token"))  # dropped
    mod._store_event("run-2", _frame(3, "tool_result"))
    mod._store_event("run-2", _frame(4, "llm_token"))  # dropped
    mod._store_event("run-2", _frame(5, "run_completed"))

    replayed = mod._replay_events("run-2", after_seq=1)
    seqs = []
    for f in replayed:
        id_line = next(ln for ln in f.split("\n") if ln.startswith("id: "))
        seqs.append(int(id_line.removeprefix("id: ")))
    # Every domain event after seq 1 is replayed; dropped token frames leave
    # holes in the seq sequence but no domain event is lost.
    assert seqs == [3, 5]


def test_token_only_run_does_not_create_empty_entry():
    _reset_store()
    mod._store_event("run-3", _frame(1, "llm_token"))
    assert "run-3" not in mod._recent_runs
