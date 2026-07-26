"""
Evaluation metrics API.
Serves data for the eval dashboard — schema validation rates,
latency stats, provider reliability, and citation coverage.
"""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from src.api.db import get_collection

router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("/summary")
async def eval_summary():
    """Return latest eval metrics summary for the dashboard."""
    runs = get_collection("runs")
    evals = get_collection("evals")

    # Get last 100 runs for stats
    recent_runs = await runs.find().sort("started_at", -1).limit(100).to_list(100)

    if not recent_runs:
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

    total = len(recent_runs)
    schema_valid = sum(1 for r in recent_runs if r.get("schema_valid", True))
    latencies = sorted([r.get("duration_ms", 0) for r in recent_runs])
    total_tool_calls = sum(r.get("tool_calls", 0) for r in recent_runs)
    total_successes = sum(r.get("tool_successes", 0) for r in recent_runs)
    total_cache_hits = sum(r.get("cache_hits", 0) for r in recent_runs)
    total_citations = sum(r.get("citations_count", 0) for r in recent_runs)

    p95_idx = int(total * 0.95)

    return {
        "total_runs": total,
        "schema_validation_rate": round(schema_valid / total * 100, 1) if total else 0,
        "avg_latency_ms": round(sum(latencies) / total) if total else 0,
        "p95_latency_ms": latencies[min(p95_idx, total - 1)] if latencies else 0,
        "citation_coverage": round(total_citations / max(total, 1), 1),
        "tool_success_rate": round(total_successes / max(total_tool_calls, 1) * 100, 1),
        "cache_hit_rate": round(total_cache_hits / max(total_tool_calls, 1) * 100, 1),
        "last_run_at": recent_runs[0].get("started_at").isoformat() if recent_runs[0].get("started_at") else None,
    }


@router.get("/history")
async def eval_history():
    """Return eval metrics over time (last 30 days, grouped by day)."""
    runs = get_collection("runs")
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    pipeline = [
        {"$match": {"started_at": {"$gte": thirty_days_ago}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$started_at"}},
            "runs": {"$sum": 1},
            "avg_latency": {"$avg": "$duration_ms"},
            "schema_valid_count": {"$sum": {"$cond": ["$schema_valid", 1, 0]}},
            "total_tokens": {"$sum": "$total_tokens"},
        }},
        {"$sort": {"_id": 1}},
    ]

    results = await runs.aggregate(pipeline).to_list(30)

    return {
        "days": [
            {
                "date": r["_id"],
                "runs": r["runs"],
                "avg_latency_ms": round(r["avg_latency"] or 0),
                "schema_validation_rate": round(r["schema_valid_count"] / max(r["runs"], 1) * 100, 1),
                "total_tokens": r["total_tokens"] or 0,
            }
            for r in results
        ]
    }
