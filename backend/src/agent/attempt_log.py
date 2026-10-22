"""Per-run record of every LLM attempt, kept for the stored trace.

Production logs last about eight minutes, so any question about why a debate
turn degraded had to be answered from memory. The chain already knows, for every
attempt, which model ran, with what settings, how long it took, what it produced
and how it ended. This module collects those facts in a per-run list that the
route writes into the traces table next to the event stream.

The list lives in a ContextVar so concurrent runs do not share it. Entries hold
operational facts only: no prompt text, no model output, and no hidden reasoning.
"""

from __future__ import annotations

import contextvars
from typing import Any

# Cap per run: three turns, a handful of attempts each, plus repairs and the report.
_MAX_ATTEMPTS = 60

_attempts: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "llm_attempt_log", default=None
)
# The debate role (bull, bear, moderator) of the call in progress, set by the caller.
_role: contextvars.ContextVar[str | None] = contextvars.ContextVar("llm_attempt_role", default=None)


def start_run() -> list[dict[str, Any]]:
    """Begin collecting attempts for the current run and return the live list."""
    fresh: list[dict[str, Any]] = []
    _attempts.set(fresh)
    return fresh


def current() -> list[dict[str, Any]] | None:
    return _attempts.get()


def set_role(role: str | None) -> None:
    _role.set(role)


def get_role() -> str | None:
    return _role.get()


def record(entry: dict[str, Any]) -> None:
    """Append one attempt. A no-op when no run is collecting, so tests and other
    callers (chat, router) never need to care."""
    bucket = _attempts.get()
    if bucket is None or len(bucket) >= _MAX_ATTEMPTS:
        return
    bucket.append({"role": _role.get(), **entry})
