"""
Per-run cost and latency tracking — PostgreSQL-backed.

Logs every analysis run for observability:
- Model used, token counts, latency, tool calls, cache hits
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from src.api.db import execute


class RunMetrics(BaseModel):
    """Metrics for a single analysis run."""

    run_id: str
    tickers: list[str]
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int = 0

    router_model: str = "llama-3.1-8b-instant"
    analysis_model: str = "llama-3.3-70b-versatile"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    tool_calls: int = 0
    tool_successes: int = 0
    tool_failures: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    cost_usd: float = 0.0

    schema_valid: bool = True
    citations_count: int = 0
    data_gaps_count: int = 0


class CostTracker:
    """Tracks metrics during a run and persists to PostgreSQL."""

    def __init__(self, run_id: str, tickers: list[str]):
        self.metrics = RunMetrics(
            run_id=run_id,
            tickers=tickers,
            started_at=datetime.now(timezone.utc),
        )
        self._start_time = time.monotonic()

    def record_tool_call(self, success: bool, cached: bool):
        self.metrics.tool_calls += 1
        if success:
            self.metrics.tool_successes += 1
        else:
            self.metrics.tool_failures += 1
        if cached:
            self.metrics.cache_hits += 1
        else:
            self.metrics.cache_misses += 1

    def record_tokens(self, prompt: int, completion: int):
        self.metrics.prompt_tokens += prompt
        self.metrics.completion_tokens += completion
        self.metrics.total_tokens += prompt + completion
        self.metrics.cost_usd += (prompt * 0.00000059) + (completion * 0.00000079)

    def record_schema_result(self, valid: bool, citations: int, data_gaps: int):
        self.metrics.schema_valid = valid
        self.metrics.citations_count = citations
        self.metrics.data_gaps_count = data_gaps

    async def persist(self):
        """Save run metrics to PostgreSQL."""
        self.metrics.completed_at = datetime.now(timezone.utc)
        self.metrics.duration_ms = int((time.monotonic() - self._start_time) * 1000)

        m = self.metrics
        await execute(
            """
            INSERT INTO runs (
                run_id, tickers, started_at, completed_at, duration_ms,
                router_model, analysis_model,
                prompt_tokens, completion_tokens, total_tokens,
                tool_calls, tool_successes, tool_failures,
                cache_hits, cache_misses, cost_usd,
                schema_valid, citations_count, data_gaps_count
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19
            )
            """,
            m.run_id, m.tickers, m.started_at, m.completed_at, m.duration_ms,
            m.router_model, m.analysis_model,
            m.prompt_tokens, m.completion_tokens, m.total_tokens,
            m.tool_calls, m.tool_successes, m.tool_failures,
            m.cache_hits, m.cache_misses, m.cost_usd,
            m.schema_valid, m.citations_count, m.data_gaps_count,
        )

    def summary(self) -> dict[str, Any]:
        """Return summary for SSE run_completed event."""
        return {
            "total_duration_ms": int((time.monotonic() - self._start_time) * 1000),
            "total_tokens": self.metrics.total_tokens,
            "cost_usd": round(self.metrics.cost_usd, 6),
            "tool_calls": self.metrics.tool_calls,
            "cache_hits": self.metrics.cache_hits,
        }
