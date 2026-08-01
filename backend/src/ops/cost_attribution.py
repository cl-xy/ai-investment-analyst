"""
Per-ticker cost attribution tracking.

Records LLM token usage and estimated cost per analysis, broken down by ticker.
Stored in PostgreSQL for ops dashboard visibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.db import execute, fetch
from src.logging_config import get_logger

log = get_logger("cost_attribution")

# OpenRouter free-tier: $0 actual cost, but track "equivalent cost" for portfolio demonstration
# Based on standard pricing: nemotron-120b ~$0.20/1M input, $0.60/1M output
# gpt-oss-20b ~$0.10/1M input, $0.30/1M output
COST_PER_1K_TOKENS = {
    "router": {"input": 0.0001, "output": 0.0003},
    "analysis": {"input": 0.0002, "output": 0.0006},
}


@dataclass
class AnalysisCostRecord:
    """Cost breakdown for a single ticker analysis."""

    ticker: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    llm_calls: int = 0
    model_breakdown: dict[str, dict] = field(default_factory=dict)
    duration_ms: int = 0


class CostAttributor:
    """Track and persist per-ticker cost attribution."""

    def __init__(self):
        self._current_session: dict[str, AnalysisCostRecord] = {}

    def start_analysis(self, ticker: str) -> None:
        """Begin tracking costs for a ticker analysis."""
        self._current_session[ticker] = AnalysisCostRecord(ticker=ticker)

    def record_llm_call(
        self,
        ticker: str,
        model_type: str,  # "router" or "analysis"
        input_tokens: int,
        output_tokens: int,
        duration_ms: int = 0,
    ) -> None:
        """Record an LLM call's token usage against a ticker."""
        if ticker not in self._current_session:
            self.start_analysis(ticker)

        record = self._current_session[ticker]
        record.input_tokens += input_tokens
        record.output_tokens += output_tokens
        record.total_tokens += input_tokens + output_tokens
        record.llm_calls += 1
        record.duration_ms += duration_ms

        # Calculate cost
        rates = COST_PER_1K_TOKENS.get(model_type, COST_PER_1K_TOKENS["analysis"])
        cost = (input_tokens / 1000 * rates["input"]) + (output_tokens / 1000 * rates["output"])
        record.estimated_cost_usd += cost

        # Model breakdown
        if model_type not in record.model_breakdown:
            record.model_breakdown[model_type] = {"calls": 0, "tokens": 0, "cost": 0.0}
        record.model_breakdown[model_type]["calls"] += 1
        record.model_breakdown[model_type]["tokens"] += input_tokens + output_tokens
        record.model_breakdown[model_type]["cost"] += cost

    async def flush(self, ticker: str, correlation_id: str | None = None) -> AnalysisCostRecord | None:
        """Persist the cost record for a completed analysis and clear session state."""
        record = self._current_session.pop(ticker, None)
        if not record:
            return None

        try:
            await execute(
                """
                INSERT INTO cost_attribution
                    (ticker, input_tokens, output_tokens, total_tokens,
                     estimated_cost_usd, llm_calls, duration_ms, correlation_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                record.ticker,
                record.input_tokens,
                record.output_tokens,
                record.total_tokens,
                record.estimated_cost_usd,
                record.llm_calls,
                record.duration_ms,
                correlation_id,
                datetime.now(timezone.utc),
            )
        except Exception as e:
            log.warning("cost_attribution_flush_failed", ticker=ticker, error=str(e))

        return record

    async def get_top_tickers(self, limit: int = 10, days: int = 7) -> list[dict]:
        """Get top tickers by total cost over the last N days."""
        rows = await fetch(
            """
            SELECT
                ticker,
                COUNT(*) as analysis_count,
                SUM(total_tokens) as total_tokens,
                SUM(estimated_cost_usd) as total_cost,
                SUM(llm_calls) as total_llm_calls,
                AVG(duration_ms) as avg_duration_ms
            FROM cost_attribution
            WHERE created_at > NOW() - INTERVAL '1 day' * $1
            GROUP BY ticker
            ORDER BY total_cost DESC
            LIMIT $2
            """,
            days,
            limit,
        )
        return [dict(row) for row in rows]

    async def get_daily_costs(self, days: int = 7) -> list[dict]:
        """Get daily cost totals for the last N days."""
        rows = await fetch(
            """
            SELECT
                DATE(created_at) as date,
                COUNT(*) as analyses,
                SUM(total_tokens) as tokens,
                SUM(estimated_cost_usd) as cost
            FROM cost_attribution
            WHERE created_at > NOW() - INTERVAL '1 day' * $1
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            """,
            days,
        )
        return [dict(row) for row in rows]


# Module singleton
cost_attributor = CostAttributor()
