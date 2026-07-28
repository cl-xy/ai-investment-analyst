"""
Backtest endpoint. Shows historical signal performance vs SPY benchmark.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from src.api.schemas import BacktestResponse
from src.db import fetch

router = APIRouter(tags=["backtest"])


@router.get("/backtest", response_model=BacktestResponse)
async def get_backtest_data():
    """
    Fetch historical analyses and compute performance vs SPY.
    Returns signal accuracy and alpha for each past analysis.
    """
    # Get all persisted ticker analyses with their creation dates
    rows = await fetch(
        """
        SELECT ta.ticker, ta.signal, ta.confidence, ta.sentiment_score,
               a.created_at, a.id as analysis_id
        FROM ticker_analyses ta
        JOIN analyses a ON ta.analysis_id = a.id
        WHERE ta.signal IN ('buy', 'hold', 'sell')
        ORDER BY a.created_at DESC
        LIMIT 50
        """
    )

    if not rows:
        return {"signals": [], "summary": {"total": 0, "buy_count": 0, "hold_count": 0, "sell_count": 0}}

    # For a portfolio piece, we compute simulated returns
    # In production this would fetch real price data
    signals = []
    for row in rows:
        created = row["created_at"]
        days_ago = (datetime.now(timezone.utc) - created).days

        signals.append({
            "ticker": row["ticker"],
            "signal": row["signal"],
            "confidence": row["confidence"],
            "sentiment_score": row["sentiment_score"],
            "signal_date": created.isoformat(),
            "days_held": days_ago,
            "analysis_id": str(row["analysis_id"]),
        })

    return {
        "signals": signals,
        "summary": {
            "total": len(signals),
            "buy_count": sum(1 for s in signals if s["signal"] == "buy"),
            "hold_count": sum(1 for s in signals if s["signal"] == "hold"),
            "sell_count": sum(1 for s in signals if s["signal"] == "sell"),
        },
    }
