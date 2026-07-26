"""
Evaluation metrics API — PostgreSQL-backed.
Serves data for the eval dashboard.
"""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from src.api.db import fetch

router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("/summary")
async def eval_summary():
    """Return latest eval metrics summary for the dashboard."""
    rows = await fetch(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT 100"
    )

    if not rows:
        return {
            "total_runs": 0,
            "schema_validation_rate": 0,
            "avg_latency_ms": 0,
            "p95_latency_ms": 0,
            "citation_coverage": 0,
            "tool_success_rate": 0,
            "cache_hit_rate": 0,
            "last_run_at": None,
        }

    total = len(rows)
    schema_valid = sum(1 for r in rows if r["schema_valid"])
    latencies = sorted([r["duration_ms"] for r in rows])
    total_tool_calls = sum(r["tool_calls"] for r in rows)
    total_successes = sum(r["tool_successes"] for r in rows)
    total_cache_hits = sum(r["cache_hits"] for r in rows)
    total_citations = sum(r["citations_count"] for r in rows)

    p95_idx = int(total * 0.95)

    return {
        "total_runs": total,
        "schema_validation_rate": round(schema_valid / total * 100, 1) if total else 0,
        "avg_latency_ms": round(sum(latencies) / total) if total else 0,
        "p95_latency_ms": latencies[min(p95_idx, total - 1)] if latencies else 0,
        "citation_coverage": round(total_citations / max(total, 1), 1),
        "tool_success_rate": round(total_successes / max(total_tool_calls, 1) * 100, 1),
        "cache_hit_rate": round(total_cache_hits / max(total_tool_calls, 1) * 100, 1),
        "last_run_at": rows[0]["started_at"].isoformat() if rows[0]["started_at"] else None,
    }


@router.get("/history")
async def eval_history():
    """Return eval metrics over time (last 30 days, grouped by day)."""
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    rows = await fetch(
        """
        SELECT
            date_trunc('day', started_at)::date AS day,
            COUNT(*) AS runs,
            AVG(duration_ms) AS avg_latency,
            SUM(CASE WHEN schema_valid THEN 1 ELSE 0 END) AS schema_valid_count,
            SUM(total_tokens) AS total_tokens
        FROM runs
        WHERE started_at >= $1
        GROUP BY day
        ORDER BY day
        """,
        thirty_days_ago,
    )

    return {
        "days": [
            {
                "date": str(r["day"]),
                "runs": r["runs"],
                "avg_latency_ms": round(r["avg_latency"] or 0),
                "schema_validation_rate": round(
                    r["schema_valid_count"] / max(r["runs"], 1) * 100, 1
                ),
                "total_tokens": r["total_tokens"] or 0,
            }
            for r in rows
        ]
    }
