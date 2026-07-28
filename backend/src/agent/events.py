"""
Domain-specific SSE event schema and LangGraph event adapter.

Decouples the frontend from LangGraph internals. Every event follows a consistent
envelope with monotonic sequence IDs for reconnection support.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    LLM_TOKEN = "llm_token"
    CITATION = "citation"
    WARNING = "warning"
    ERROR = "error"
    ANALYSIS_COMPLETE = "analysis_complete"
    RUN_COMPLETED = "run_completed"
    HEARTBEAT = "heartbeat"
    # Adversarial debate events
    DEBATE_STARTED = "debate_started"
    DEBATE_TURN = "debate_turn"
    DEBATE_VERDICT = "debate_verdict"


class StreamEvent(BaseModel):
    """Envelope for all SSE events sent to the frontend."""

    run_id: str = Field(description="UUID identifying this analysis run")
    seq: int = Field(description="Monotonic sequence ID for reconnection")
    type: EventType
    timestamp: str = Field(description="ISO 8601 timestamp")
    node: str | None = None
    tool: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Format as an SSE message with id, event, and data fields."""
        lines = [
            f"id: {self.seq}",
            f"event: {self.type.value}",
            f"data: {self.model_dump_json()}",
            "",
            "",
        ]
        return "\n".join(lines)


class EventEmitter:
    """Tracks sequence numbering and emits typed events for a single run."""

    def __init__(self, run_id: str | None = None):
        self.run_id = run_id or str(uuid.uuid4())
        self._seq = 0
        self._events: list[StreamEvent] = []
        self._node_start_times: dict[str, float] = {}

    @property
    def events(self) -> list[StreamEvent]:
        return self._events

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _emit(
        self,
        event_type: EventType,
        node: str | None = None,
        tool: str | None = None,
        payload: dict | None = None,
    ) -> StreamEvent:
        event = StreamEvent(
            run_id=self.run_id,
            seq=self._next_seq(),
            type=event_type,
            timestamp=self._now(),
            node=node,
            tool=tool,
            payload=payload or {},
        )
        self._events.append(event)
        return event

    def run_started(self, tickers: list[str]) -> StreamEvent:
        return self._emit(EventType.RUN_STARTED, payload={"tickers": tickers})

    def node_started(self, node_name: str) -> StreamEvent:
        self._node_start_times[node_name] = time.monotonic()
        return self._emit(EventType.NODE_STARTED, node=node_name, payload={"node_name": node_name})

    def node_completed(self, node_name: str) -> StreamEvent:
        start = self._node_start_times.pop(node_name, None)
        duration_ms = int((time.monotonic() - start) * 1000) if start else 0
        return self._emit(
            EventType.NODE_COMPLETED,
            node=node_name,
            payload={"node_name": node_name, "duration_ms": duration_ms},
        )

    def tool_call(self, tool_name: str, args: dict, node: str | None = None) -> StreamEvent:
        return self._emit(
            EventType.TOOL_CALL,
            node=node,
            tool=tool_name,
            payload={"tool_name": tool_name, "args": args},
        )

    def tool_result(
        self,
        tool_name: str,
        *,
        success: bool,
        cached: bool = False,
        duration_ms: int = 0,
        source_id: str = "",
        node: str | None = None,
        no_data: bool = False,
    ) -> StreamEvent:
        return self._emit(
            EventType.TOOL_RESULT,
            node=node,
            tool=tool_name,
            payload={
                "tool_name": tool_name,
                "success": success,
                "cached": cached,
                "duration_ms": duration_ms,
                "source_id": source_id,
                "no_data": no_data,
            },
        )

    def llm_token(self, text: str, node: str | None = None) -> StreamEvent:
        return self._emit(EventType.LLM_TOKEN, node=node, payload={"text": text})

    def citation(self, source_id: str, claim: str, provider: str) -> StreamEvent:
        return self._emit(
            EventType.CITATION,
            payload={"source_id": source_id, "claim": claim, "provider": provider},
        )

    def warning(self, message: str, context: str = "") -> StreamEvent:
        return self._emit(EventType.WARNING, payload={"message": message, "context": context})

    def error(self, message: str, recoverable: bool = True, context: str = "") -> StreamEvent:
        return self._emit(
            EventType.ERROR,
            payload={"message": message, "recoverable": recoverable, "context": context},
        )

    def analysis_complete(self, ticker: str, analysis: dict) -> StreamEvent:
        return self._emit(
            EventType.ANALYSIS_COMPLETE,
            payload={"ticker": ticker, "analysis": analysis},
        )

    def run_completed(
        self,
        tickers: list[str],
        total_duration_ms: int,
        total_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> StreamEvent:
        return self._emit(
            EventType.RUN_COMPLETED,
            payload={
                "tickers": tickers,
                "total_duration_ms": total_duration_ms,
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
            },
        )

    def heartbeat(self) -> StreamEvent:
        return self._emit(EventType.HEARTBEAT)

    # Adversarial debate events

    def debate_started(self, ticker: str, agents: list[str]) -> StreamEvent:
        return self._emit(
            EventType.DEBATE_STARTED,
            node="debate",
            payload={"ticker": ticker, "agents": agents},
        )

    def debate_turn(
        self,
        ticker: str,
        role: str,
        thesis: str,
        confidence: str,
        key_arguments: list[str],
        turn_index: int,
        duration_ms: int = 0,
    ) -> StreamEvent:
        return self._emit(
            EventType.DEBATE_TURN,
            node="debate",
            payload={
                "ticker": ticker,
                "role": role,
                "thesis": thesis,
                "confidence": confidence,
                "key_arguments": key_arguments,
                "turn_index": turn_index,
                "duration_ms": duration_ms,
            },
        )

    def debate_verdict(
        self,
        ticker: str,
        signal: str,
        confidence: str,
        verdict_rationale: str,
        key_disagreements: list[str],
        duration_ms: int = 0,
    ) -> StreamEvent:
        return self._emit(
            EventType.DEBATE_VERDICT,
            node="debate",
            payload={
                "ticker": ticker,
                "signal": signal,
                "confidence": confidence,
                "verdict_rationale": verdict_rationale,
                "key_disagreements": key_disagreements,
                "duration_ms": duration_ms,
            },
        )
