"""
Lightweight in-memory metrics collection.

No external dependencies. Fixed-size sliding window for histograms.
Resets on restart. For operational visibility, not production monitoring.

Usage:
    from src.metrics import metrics
    metrics.inc("analyses_total", labels={"status": "success"})
    metrics.observe("analysis_duration_seconds", 2.3, labels={"ticker": "AAPL"})
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter

router = APIRouter()

# Sliding window size for histograms
_WINDOW_SIZE = 1000


@dataclass
class Counter:
    """Simple counter with labels."""

    _values: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, labels: dict[str, str] | None = None, amount: int = 1) -> None:
        key = _label_key(labels)
        with self._lock:
            self._values[key] += amount

    def get(self, labels: dict[str, str] | None = None) -> int:
        key = _label_key(labels)
        with self._lock:
            return self._values.get(key, 0)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._values)


@dataclass
class Histogram:
    """Fixed-size sliding window histogram with percentile calculation."""

    _observations: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = _label_key(labels)
        with self._lock:
            obs = self._observations[key]
            obs.append(value)
            # Keep only the last N observations
            if len(obs) > _WINDOW_SIZE:
                self._observations[key] = obs[-_WINDOW_SIZE:]

    def percentiles(self, labels: dict[str, str] | None = None) -> dict[str, float | int]:
        key = _label_key(labels)
        with self._lock:
            obs = list(self._observations.get(key, []))

        if not obs:
            return {"count": 0, "p50": 0, "p95": 0, "p99": 0}

        obs.sort()
        n = len(obs)
        return {
            "count": n,
            "p50": round(obs[int(n * 0.50)], 3),
            "p95": round(obs[min(int(n * 0.95), n - 1)], 3),
            "p99": round(obs[min(int(n * 0.99), n - 1)], 3),
        }

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        with self._lock:
            keys = list(self._observations.keys())

        result = {}
        for key in keys:
            result[key] = self.percentiles(_parse_label_key(key))
        return result


def _label_key(labels: dict[str, str] | None) -> str:
    """Create a stable string key from label dict."""
    if not labels:
        return ""
    return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))


def _parse_label_key(key: str) -> dict[str, str] | None:
    """Parse a label key back to a dict (for snapshot iteration)."""
    if not key:
        return None
    result = {}
    for part in key.split(","):
        k, v = part.split("=", 1)
        result[k] = v
    return result


class MetricsRegistry:
    """Central registry for all application metrics."""

    def __init__(self):
        self._started_at = time.time()

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

    def observe(self, histogram_name: str, value: float, labels: dict[str, str] | None = None) -> None:
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
            "uptime_seconds": round(time.time() - self._started_at, 1),
        }


# Singleton instance
metrics = MetricsRegistry()


@router.get("/metrics")
async def get_metrics():
    """Expose in-memory metrics as JSON."""
    return metrics.snapshot()
