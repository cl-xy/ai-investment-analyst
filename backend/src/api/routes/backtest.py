"""
Backtest endpoint. Returns historical signal data for past analyses.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from src.api.schemas import BacktestResponse
from src.db import fetch

logger = logging.getLogger(__name__)

router = APIRouter(tags=["backtest"])


@router.get("/backtest", response_model=BacktestResponse)
async def get_backtest_data():
    """
    Fetch historical analyses and return signal history.
    Returns past signals with holding period and summary counts.
    """
    try:
        rows = await fetch(
            """
            SELECT ta.ticker, ta.signal, ta.confidence, ta.sentiment_score,
                   a.created_at, a.id as analysis_id
            FROM ticker_analyses ta
            JOIN analyses a ON ta.analysis_id = a.id
            WHERE ta.signal IN ('buy', 'hold', 'sell')
              AND a.created_at IS NOT NULL
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT 50
            """
        )
    except Exception:
        logger.exception("Failed to fetch backtest data")
        raise HTTPException(status_code=503, detail="Backtest data temporarily unavailable")

    if not rows:
        return {
            "signals": [],
            "summary": {"total": 0, "buy_count": 0, "hold_count": 0, "sell_count": 0},
        }

    now = datetime.now(timezone.utc)
    signals = []
    for row in rows:
        created = row["created_at"]
        if created is None:
            continue
        # Normalize timezone-naive timestamps (asyncpg returns naive for TIMESTAMP WITHOUT TIME ZONE)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        days_ago = max(0, (now - created).days)

        signals.append(
            {
                "ticker": row["ticker"],
                "signal": row["signal"],
                "confidence": row["confidence"],
                "sentiment_score": row["sentiment_score"],
                "signal_date": created.isoformat(),
                "days_held": days_ago,
                "analysis_id": str(row["analysis_id"]),
            }
        )

    return {
        "signals": signals,
        "summary": {
            "total": len(signals),
            "buy_count": sum(1 for s in signals if s["signal"] == "buy"),
            "hold_count": sum(1 for s in signals if s["signal"] == "hold"),
            "sell_count": sum(1 for s in signals if s["signal"] == "sell"),
        },
    }
