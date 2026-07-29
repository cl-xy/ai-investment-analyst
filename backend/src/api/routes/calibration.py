"""
Prediction tracking and calibration (Layer 3: Track Record).

Records every investment signal as a prediction, resolves outcomes after
the horizon elapses, and computes calibration metrics (Brier score,
hit rate by confidence bucket).
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from src.db import execute, fetch, fetchval

log = logging.getLogger(__name__)

router = APIRouter()


async def record_prediction(
    analysis_id: uuid.UUID | None,
    ticker: str,
    signal: str,
    confidence: str,
    sentiment_score: float,
    thesis: str,
    price_at_prediction: float | None,
    horizon_days: int = 30,
) -> uuid.UUID:
    """Record a new prediction from an analysis run. Called internally after debate."""
    pred_id = uuid.uuid4()
    await execute(
        """
        INSERT INTO predictions (id, analysis_id, ticker, signal, confidence, sentiment_score, thesis, price_at_prediction, horizon_days)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        pred_id,
        analysis_id,
        ticker,
        signal,
        confidence,
        sentiment_score,
        thesis,
        price_at_prediction,
        horizon_days,
    )
    return pred_id


@router.get("/calibration")
async def get_calibration(
    ticker: str | None = Query(None, description="Filter by ticker"),
    horizon_days: int = Query(30, description="Prediction horizon in days"),
):
    """
    Get calibration metrics for resolved predictions.

    Returns hit rate by confidence bucket, Brier score, and signal accuracy.
    """
    # Fetch resolved predictions
    if ticker:
        rows = await fetch(
            """
            SELECT signal, confidence, outcome, realized_return
            FROM predictions
            WHERE resolved_at IS NOT NULL AND horizon_days = $1 AND ticker = $2
            ORDER BY created_at DESC
            """,
            horizon_days,
            ticker.upper(),
        )
    else:
        rows = await fetch(
            """
            SELECT signal, confidence, outcome, realized_return
            FROM predictions
            WHERE resolved_at IS NOT NULL AND horizon_days = $1
            ORDER BY created_at DESC
            """,
            horizon_days,
        )

    if not rows:
        return {
            "status": "insufficient_data",
            "total_predictions": 0,
            "resolved": 0,
            "message": "Not enough resolved predictions for calibration",
        }

    # Compute metrics
    total = len(rows)
    correct = sum(1 for r in rows if r["outcome"] == "correct")
    _ = sum(1 for r in rows if r["outcome"] == "incorrect")  # noqa: F841

    # Hit rate by confidence bucket
    confidence_buckets: dict[str, list[int]] = {"high": [], "medium": [], "low": []}
    for row in rows:
        bucket = row["confidence"]
        if bucket in confidence_buckets:
            confidence_buckets[bucket].append(1 if row["outcome"] == "correct" else 0)

    calibration = {}
    for bucket, outcomes in confidence_buckets.items():
        if outcomes:
            calibration[bucket] = {
                "count": len(outcomes),
                "hit_rate": sum(outcomes) / len(outcomes),
            }

    # Signal accuracy
    signal_stats = {}
    for row in rows:
        sig = row["signal"]
        if sig not in signal_stats:
            signal_stats[sig] = {"total": 0, "correct": 0}
        signal_stats[sig]["total"] += 1
        if row["outcome"] == "correct":
            signal_stats[sig]["correct"] += 1

    for sig, stats in signal_stats.items():
        stats["accuracy"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0  # type: ignore[assignment]

    # Brier score (lower is better, 0 = perfect)
    # Map confidence to probability: high=0.8, medium=0.5, low=0.3
    confidence_to_prob = {"high": 0.80, "medium": 0.55, "low": 0.30}
    brier_sum = 0.0
    brier_count = 0
    for row in rows:
        prob = confidence_to_prob.get(row["confidence"], 0.5)
        actual = 1.0 if row["outcome"] == "correct" else 0.0
        brier_sum += (prob - actual) ** 2
        brier_count += 1

    brier_score = brier_sum / brier_count if brier_count > 0 else None

    # Unresolved count
    unresolved = await fetchval(
        "SELECT COUNT(*) FROM predictions WHERE resolved_at IS NULL AND horizon_days = $1",
        horizon_days,
    )

    return {
        "status": "ok",
        "horizon_days": horizon_days,
        "total_predictions": total + (unresolved or 0),
        "resolved": total,
        "unresolved": unresolved or 0,
        "overall_accuracy": correct / total if total > 0 else 0,
        "brier_score": round(brier_score, 4) if brier_score is not None else None,
        "calibration_by_confidence": calibration,
        "accuracy_by_signal": signal_stats,
    }


@router.get("/calibration/predictions")
async def list_predictions(
    ticker: str | None = Query(None),
    resolved: bool | None = Query(None, description="Filter by resolution status"),
    limit: int = Query(50, le=200),
):
    """List predictions with optional filters."""
    conditions: list[str] = []
    params: list[str | int] = []
    idx = 1

    if ticker:
        conditions.append(f"ticker = ${idx}")
        params.append(ticker.upper())
        idx += 1

    if resolved is True:
        conditions.append("resolved_at IS NOT NULL")
    elif resolved is False:
        conditions.append("resolved_at IS NULL")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = await fetch(  # nosemgrep: sql-string-interpolation
        f"""
        SELECT id, ticker, signal, confidence, sentiment_score, thesis,
               price_at_prediction, horizon_days, created_at,
               resolved_at, outcome_price, realized_return, outcome
        FROM predictions
        {where}
        ORDER BY created_at DESC
        LIMIT ${idx}
        """,
        *params,
    )

    return [
        {
            "id": str(row["id"]),
            "ticker": row["ticker"],
            "signal": row["signal"],
            "confidence": row["confidence"],
            "sentiment_score": row["sentiment_score"],
            "thesis": row["thesis"],
            "price_at_prediction": row["price_at_prediction"],
            "horizon_days": row["horizon_days"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
            "outcome_price": row["outcome_price"],
            "realized_return": row["realized_return"],
            "outcome": row["outcome"],
        }
        for row in rows
    ]


@router.post("/calibration/resolve")
async def resolve_predictions():
    """
    Resolve pending predictions whose horizon has elapsed.

    Fetches current price and computes outcome. Called via scheduled job or manually.
    Returns count of newly resolved predictions.
    """
    import asyncio

    import yfinance as yf

    from src.db import get_pool

    pool = await get_pool()

    def _fetch_price(ticker: str) -> float | None:
        """Fetch current price via yfinance (sync, runs in thread pool)."""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d", timeout=15)
            if hist.empty:
                return None
            return float(hist["Close"].iloc[-1])
        except Exception as exc:
            log.warning("resolve_price_fetch_failed ticker=%s error=%s", ticker, exc)
            return None

    # Use a single connection + transaction so FOR UPDATE SKIP LOCKED
    # holds row locks until all updates complete (prevents concurrent resolution).
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, ticker, signal, price_at_prediction, horizon_days, created_at
                FROM predictions
                WHERE resolved_at IS NULL
                  AND created_at + (horizon_days || ' days')::interval <= now()
                LIMIT 50
                FOR UPDATE SKIP LOCKED
                """,
            )

            if not rows:
                return {"resolved_count": 0, "message": "No predictions ready for resolution"}

            resolved_count = 0
            for row in rows:
                ticker = row["ticker"]
                prediction_price = row["price_at_prediction"]

                if prediction_price is None:
                    continue

                # Run sync yfinance in thread pool with a timeout to avoid
                # holding row locks indefinitely on a hung upstream call
                try:
                    current_price = await asyncio.wait_for(
                        asyncio.to_thread(_fetch_price, ticker), timeout=20
                    )
                except asyncio.TimeoutError:
                    log.warning("resolve_price_timeout ticker=%s", ticker)
                    current_price = None
                if current_price is None:
                    continue

                # Compute return
                realized_return = (current_price - prediction_price) / prediction_price

                # Determine outcome based on signal
                signal = row["signal"]
                if signal == "buy":
                    outcome = (
                        "correct"
                        if realized_return > 0.02
                        else ("incorrect" if realized_return < -0.02 else "neutral")
                    )
                elif signal == "sell":
                    outcome = (
                        "correct"
                        if realized_return < -0.02
                        else ("incorrect" if realized_return > 0.02 else "neutral")
                    )
                else:
                    # hold: correct if price stayed within +/-5%
                    outcome = "correct" if abs(realized_return) < 0.05 else "incorrect"

                await conn.execute(
                    """
                    UPDATE predictions
                    SET resolved_at = $1, outcome_price = $2, realized_return = $3, outcome = $4
                    WHERE id = $5
                    """,
                    datetime.now(timezone.utc),
                    current_price,
                    realized_return,
                    outcome,
                    row["id"],
                )
                resolved_count += 1

    return {"resolved_count": resolved_count}
