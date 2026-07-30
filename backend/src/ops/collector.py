"""
Metrics collector singleton for the ops dashboard.

Tracks request latencies (histogram buckets), counts by endpoint/status,
LLM call durations and token counts, circuit breaker state changes,
and rolling SLO metrics (7-day window).

Stores recent traces in memory (last 50) and persists summaries to Postgres.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.logging_config import get_logger

log = get_logger("ops.collector")

_ROLLING_WINDOW_SECONDS = 7 * 24 * 3600  # 7 days
_MAX_RECENT_TRACES = 50


@dataclass
class RequestRecord:
    """Single request observation for SLO computation."""

    timestamp: float
    endpoint: str
    status_code: int
    duration_ms: float


@dataclass
class CircuitBreakerEvent:
    """Circuit breaker state transition."""

    timestamp: float
    breaker_name: str
    from_state: str
    to_state: str


@dataclass
class TraceRecord:
    """In-memory trace summary for recent traces list."""

    correlation_id: str
    ticker: str
    started_at: float
    duration_ms: float
    status: str  # success, degraded, failed
    events: list[dict[str, Any]]


class OpsCollector:
    """Central ops metrics collector. Thread-safe singleton."""

    def __init__(self):
        self._lock = threading.Lock()
        self._started_at = time.time()

        # Request tracking (rolling window for SLO)
        self._requests: deque[RequestRecord] = deque()

        # Counters by endpoint and status
        self._request_counts: dict[str, int] = defaultdict(int)
        self._error_counts: dict[str, int] = defaultdict(int)

        # Latency observations (sliding window, last 1000)
        self._latencies: deque[float] = deque(maxlen=1000)

        # LLM call tracking
        self._llm_durations: deque[float] = deque(maxlen=500)
        self._llm_call_count: int = 0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0

        # Circuit breaker events
        self._cb_events: deque[CircuitBreakerEvent] = deque(maxlen=100)
        self._cb_current_states: dict[str, str] = {}

        # Cache tracking
        self._cache_hits: int = 0
        self._cache_misses: int = 0

        # Recent traces (in-memory ring buffer)
        self._recent_traces: deque[TraceRecord] = deque(maxlen=_MAX_RECENT_TRACES)

        # SLO targets
        self.slo_targets = {
            "availability": 0.995,  # 99.5%
            "latency_p95_ms": 120_000,  # 120s (debate is slow on free tier)
            "error_budget_monthly": 0.005,  # 0.5% error budget
        }

    def record_request(
        self,
        endpoint: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """Record a completed request for metrics and SLO computation."""
        now = time.time()
        record = RequestRecord(
            timestamp=now,
            endpoint=endpoint,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        with self._lock:
            self._requests.append(record)
            self._latencies.append(duration_ms)
            key = f"{endpoint}"
            self._request_counts[key] += 1
            if status_code >= 500:
                self._error_counts[key] += 1
            # Trim old entries outside 7-day window
            cutoff = now - _ROLLING_WINDOW_SECONDS
            while self._requests and self._requests[0].timestamp < cutoff:
                self._requests.popleft()

    def record_llm_call(
        self,
        duration_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model: str = "",
    ) -> None:
        """Record an LLM API call with timing and token usage."""
        with self._lock:
            self._llm_durations.append(duration_ms)
            self._total_prompt_tokens += prompt_tokens
            self._total_completion_tokens += completion_tokens
            self._llm_call_count += 1

    def record_circuit_breaker_change(
        self, breaker_name: str, from_state: str, to_state: str
    ) -> None:
        """Record a circuit breaker state transition."""
        event = CircuitBreakerEvent(
            timestamp=time.time(),
            breaker_name=breaker_name,
            from_state=from_state,
            to_state=to_state,
        )
        with self._lock:
            self._cb_events.append(event)
            self._cb_current_states[breaker_name] = to_state

    def record_cache_access(self, hit: bool) -> None:
        """Record a cache hit or miss."""
        with self._lock:
            if hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

    def record_trace(self, trace: TraceRecord) -> None:
        """Store a completed trace in the recent buffer."""
        with self._lock:
            self._recent_traces.append(trace)

    def get_metrics(self) -> dict[str, Any]:
        """Return current system metrics snapshot."""
        with self._lock:
            total_requests = sum(self._request_counts.values())
            total_errors = sum(self._error_counts.values())

            # Copy data under lock, sort outside
            latencies_copy = list(self._latencies)
            llm_durations_copy = list(self._llm_durations)
            total_prompt_tokens = self._total_prompt_tokens
            total_completion_tokens = self._total_completion_tokens
            llm_call_count = self._llm_call_count
            cb_states = dict(self._cb_current_states)
            cache_hits = self._cache_hits
            cache_misses = self._cache_misses
            by_endpoint = dict(self._request_counts)
            errors_by_endpoint = dict(self._error_counts)

        # Latency percentiles (outside lock)
        latencies = sorted(latencies_copy)
        n = len(latencies)
        if n > 0:
            p50 = latencies[min(int(n * 0.50), n - 1)]
            p95 = latencies[min(int(n * 0.95), n - 1)]
        else:
            p50 = 0.0
            p95 = 0.0

        # LLM metrics (outside lock)
        llm_durations = sorted(llm_durations_copy)
        llm_n = len(llm_durations)
        if llm_n > 0:
            llm_p50 = llm_durations[min(int(llm_n * 0.50), llm_n - 1)]
            llm_p95 = llm_durations[min(int(llm_n * 0.95), llm_n - 1)]
        else:
            llm_p50 = 0.0
            llm_p95 = 0.0

        # Cache hit rate
        cache_total = cache_hits + cache_misses
        cache_hit_rate = (cache_hits / cache_total) if cache_total > 0 else 0.0

        return {
            "requests": {
                "total": total_requests,
                "errors": total_errors,
                "by_endpoint": by_endpoint,
                "errors_by_endpoint": errors_by_endpoint,
            },
            "latency": {
                "p50_ms": round(p50, 1),
                "p95_ms": round(p95, 1),
                "observations": n,
            },
            "llm": {
                "total_calls": llm_call_count,
                "duration_p50_ms": round(llm_p50, 1),
                "duration_p95_ms": round(llm_p95, 1),
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
            },
            "circuit_breakers": cb_states,
            "cache": {
                "hits": cache_hits,
                "misses": cache_misses,
                "hit_rate": round(cache_hit_rate, 4),
            },
            "uptime_seconds": round(time.time() - self._started_at, 1),
        }

    def get_recent_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent traces."""
        if limit <= 0:
            return []
        with self._lock:
            traces = list(self._recent_traces)[-limit:]
        return [
            {
                "correlation_id": t.correlation_id,
                "ticker": t.ticker,
                "started_at": datetime.fromtimestamp(t.started_at, tz=timezone.utc).isoformat(),
                "duration_ms": t.duration_ms,
                "status": t.status,
                "event_count": len(t.events),
                "events": t.events,
            }
            for t in reversed(traces)
        ]

    def compute_slo(self) -> dict[str, Any]:
        """Compute SLO targets vs actuals over the rolling 7-day window."""
        with self._lock:
            # Trim stale records before computing (traffic may have stopped)
            cutoff = time.time() - _ROLLING_WINDOW_SECONDS
            while self._requests and self._requests[0].timestamp < cutoff:
                self._requests.popleft()
            records = list(self._requests)

        total = len(records)
        if total == 0:
            return {
                "window": "7d",
                "total_requests": 0,
                "targets": self.slo_targets,
                "actuals": {
                    "availability": 1.0,
                    "latency_p95_ms": 0.0,
                    "error_rate": 0.0,
                },
                "budget": {
                    "error_budget_total": self.slo_targets["error_budget_monthly"],
                    "error_budget_consumed": 0.0,
                    "error_budget_remaining": self.slo_targets["error_budget_monthly"],
                    "burn_rate": 0.0,
                },
                "status": "healthy",
            }

        # Availability: non-5xx / total
        successful = sum(1 for r in records if r.status_code < 500)
        availability = successful / total

        # Latency P95
        latencies = sorted(r.duration_ms for r in records)
        n = len(latencies)
        latency_p95 = latencies[min(int(n * 0.95), n - 1)]

        # Error rate
        error_rate = 1.0 - availability

        # Error budget burn
        budget_total = self.slo_targets["error_budget_monthly"]
        # Budget consumed as fraction of allowed budget
        budget_consumed = min(error_rate, budget_total)
        budget_remaining = max(0.0, budget_total - budget_consumed)

        # Burn rate: ratio of observed error rate to allowed error rate
        # burn_rate = 1.0 means consuming budget at exactly the sustainable pace
        # burn_rate > 1.0 means budget will be exhausted before the month ends
        burn_rate = (error_rate / budget_total) if budget_total > 0 else 0.0

        # Determine overall SLO status (check critical first to avoid masking)
        if burn_rate > 2.0:
            slo_status = "critical"
        elif (
            availability < self.slo_targets["availability"]
            or latency_p95 > self.slo_targets["latency_p95_ms"]
        ):
            slo_status = "at_risk"
        else:
            slo_status = "healthy"

        return {
            "window": "7d",
            "total_requests": total,
            "targets": self.slo_targets,
            "actuals": {
                "availability": round(availability, 6),
                "latency_p95_ms": round(latency_p95, 1),
                "error_rate": round(error_rate, 6),
            },
            "budget": {
                "error_budget_total": budget_total,
                "error_budget_consumed": round(budget_consumed, 6),
                "error_budget_remaining": round(budget_remaining, 6),
                "burn_rate": round(burn_rate, 2),
            },
            "status": slo_status,
        }

    async def persist_metrics_snapshot(self) -> None:
        """Persist current metrics to Postgres for historical SLO computation."""
        from src.db import execute

        snapshot = self.get_metrics()
        try:
            await execute(
                """
                INSERT INTO ops_metrics_snapshots (recorded_at, metrics)
                VALUES (NOW(), $1)
                """,
                json.dumps(snapshot, allow_nan=False),
            )
        except Exception as exc:
            log.warning("metrics_snapshot_persist_failed", error=str(exc))


# Singleton
collector = OpsCollector()
