"""
Lightweight in-memory metrics collection.

No external dependencies. Fixed-size sliding window for histograms.
Resets on restart. For operational visibility, not production monitoring.
Metrics are per-process (not aggregated across workers).

Usage:
    from src.metrics import metrics
    metrics.inc("analyses_total", labels={"status": "success"})
    metrics.observe("analysis_duration_seconds", 2.3, labels={"ticker": "AAPL"})
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter

router = APIRouter()

# Sliding window size for histograms
_WINDOW_SIZE = 1000

# Max distinct label combinations per metric (bounds memory)
_MAX_CARDINALITY = 1000

# Type alias for the internal canonical label key
_LabelKey = tuple[tuple[str, str], ...]


def _label_key(labels: dict[str, str] | None) -> _LabelKey:
    """Create a collision-free canonical key from label dict.

    Uses a sorted tuple of (key, value) pairs, avoiding delimiter-based
    serialization that breaks on values containing commas or equals signs.
    """
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _label_key_to_str(key: _LabelKey) -> str:
    """Render a label key as a human-readable string for JSON export."""
    if not key:
        return ""
    return ",".join(f"{k}={v}" for k, v in key)


@dataclass
class Counter:
    """Simple counter with labels."""

    _values: dict[_LabelKey, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def inc(self, labels: dict[str, str] | None = None, amount: int = 1) -> None:
        key = _label_key(labels)
        with self._lock:
            if key not in self._values and len(self._values) >= _MAX_CARDINALITY:
                return  # drop to prevent memory DoS
            self._values[key] = self._values.get(key, 0) + amount

    def get(self, labels: dict[str, str] | None = None) -> int:
        key = _label_key(labels)
        with self._lock:
            return self._values.get(key, 0)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {_label_key_to_str(k): v for k, v in self._values.items()}


@dataclass
class Histogram:
    """Fixed-size sliding window histogram with percentile calculation."""

    _observations: dict[_LabelKey, deque] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return  # reject NaN, Inf, non-numeric
        key = _label_key(labels)
        with self._lock:
            if key not in self._observations:
                if len(self._observations) >= _MAX_CARDINALITY:
                    return  # drop to prevent memory DoS
                self._observations[key] = deque(maxlen=_WINDOW_SIZE)
            self._observations[key].append(float(value))

    def percentiles(self, labels: dict[str, str] | None = None) -> dict[str, float | int]:
        """Compute percentiles for a specific label set."""
        key = _label_key(labels)
        with self._lock:
            raw = self._observations.get(key)
            obs = list(raw) if raw else []

        return _compute_percentiles(obs)

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        """Atomic snapshot: copy all data under one lock, compute outside."""
        with self._lock:
            copied = {k: list(v) for k, v in self._observations.items()}

        return {_label_key_to_str(k): _compute_percentiles(v) for k, v in copied.items()}


def _compute_percentiles(obs: list[float]) -> dict[str, float | int]:
    """Compute p50/p95/p99 from a list of observations."""
    if not obs:
        return {"count": 0, "p50": 0, "p95": 0, "p99": 0}

    obs.sort()
    n = len(obs)
    return {
        "count": n,
        "p50": round(obs[min(int(n * 0.50), n - 1)], 3),
        "p95": round(obs[min(int(n * 0.95), n - 1)], 3),
        "p99": round(obs[min(int(n * 0.99), n - 1)], 3),
    }


class MetricsRegistry:
    """Central registry for all application metrics."""

    def __init__(self):
        self._started_at = time.monotonic()

        # Counters
        self.analyses_total = Counter()
        self.tool_calls_total = Counter()
        self.llm_calls_total = Counter()
        self.circuit_breaker_trips = Counter()

        # Histograms
        self.analysis_duration_seconds = Histogram()
        self.tool_call_duration_seconds = Histogram()
        self.llm_call_duration_seconds = Histogram()
        self.token_usage = Histogram()

    def inc(self, counter_name: str, labels: dict[str, str] | None = None, amount: int = 1) -> None:
        """Increment a counter by name."""
        counter = getattr(self, counter_name, None)
        if isinstance(counter, Counter):
            counter.inc(labels, amount)

    def observe(
        self, histogram_name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Record an observation in a histogram by name."""
        hist = getattr(self, histogram_name, None)
        if isinstance(hist, Histogram):
            hist.observe(value, labels)

    def snapshot(self) -> dict[str, Any]:
        """Return full metrics snapshot as JSON-serializable dict."""
        return {
            "counters": {
                "analyses_total": self.analyses_total.snapshot(),
                "tool_calls_total": self.tool_calls_total.snapshot(),
                "llm_calls_total": self.llm_calls_total.snapshot(),
                "circuit_breaker_trips": self.circuit_breaker_trips.snapshot(),
            },
            "histograms": {
                "analysis_duration_seconds": self.analysis_duration_seconds.snapshot(),
                "tool_call_duration_seconds": self.tool_call_duration_seconds.snapshot(),
                "llm_call_duration_seconds": self.llm_call_duration_seconds.snapshot(),
                "token_usage": self.token_usage.snapshot(),
            },
            "window": "last_1000_observations",
            "uptime_seconds": round(time.monotonic() - self._started_at, 1),
        }


# Singleton instance
metrics = MetricsRegistry()


@router.get("/metrics")
async def get_metrics():
    """Expose in-memory metrics as JSON."""
    return metrics.snapshot()
