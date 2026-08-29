"""
Prediction tracking and calibration (Layer 3: Track Record).

Records every investment signal as a prediction, resolves outcomes after
the horizon elapses, and computes calibration metrics (Brier score,
hit rate by confidence bucket).
"""

import logging
import uuid
from datetime import datetime, timezone
from secrets import compare_digest

from fastapi import APIRouter, Header, HTTPException, Query

from src.config import settings
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
    horizon_days: int = Query(30, ge=1, le=3650, description="Prediction horizon in days"),
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

    # Unresolved count (apply same ticker filter if provided)
    if ticker:
        unresolved = await fetchval(
            "SELECT COUNT(*) FROM predictions WHERE resolved_at IS NULL AND horizon_days = $1 AND ticker = $2",
            horizon_days,
            ticker.upper(),
        )
    else:
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
    limit: int = Query(50, ge=1, le=200),
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


def _fetch_adjusted_price(ticker: str, target_date: datetime) -> float | None:
    """Fetch adjusted close price at or near target date via yfinance."""
    from datetime import timedelta

    import yfinance as yf

    try:
        stock = yf.Ticker(ticker)
        start = target_date - timedelta(days=5)
        end = target_date + timedelta(days=3)
        hist = stock.history(
            start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), timeout=15
        )
        if hist.empty:
            return None
        target_str = target_date.strftime("%Y-%m-%d")
        after = hist[hist.index >= target_str]
        if not after.empty:
            return float(after["Close"].iloc[0])
        return float(hist["Close"].iloc[-1])
    except Exception as exc:
        log.warning("resolve_price_fetch_failed ticker=%s error=%s", ticker, exc)
        return None


def _fetch_benchmark_return(prediction_date: datetime, resolution_date: datetime) -> float | None:
    """Fetch SPY return over the same period as the prediction horizon."""
    from datetime import timedelta

    import yfinance as yf

    try:
        spy = yf.Ticker("SPY")
        start = prediction_date - timedelta(days=5)
        end = resolution_date + timedelta(days=3)
        hist = spy.history(
            start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), timeout=15
        )
        if len(hist) < 2:
            return None
        pred_str = prediction_date.strftime("%Y-%m-%d")
        res_str = resolution_date.strftime("%Y-%m-%d")
        pred_prices = hist[hist.index <= pred_str]
        res_prices = hist[hist.index >= res_str]
        if pred_prices.empty or res_prices.empty:
            return None
        spy_at_pred = float(pred_prices["Close"].iloc[-1])
        spy_at_res = float(res_prices["Close"].iloc[0])
        return (spy_at_res - spy_at_pred) / spy_at_pred if spy_at_pred > 0 else None
    except Exception as exc:
        log.warning("benchmark_fetch_failed error=%s", exc)
        return None


def _determine_outcome(signal: str, check_return: float, is_excess: bool = False) -> str:
    """Determine prediction outcome based on signal and return.

    Args:
        signal: The predicted signal (buy/sell/hold)
        check_return: The return value to check against thresholds
        is_excess: If True, check_return is benchmark-relative (excess return).
                   Thresholds are tighter for excess returns since they measure
                   alpha, not raw market movement.
    """
    # Excess return thresholds: smaller because alpha is harder to generate
    # Absolute return thresholds: larger because they include market beta
    threshold = 0.01 if is_excess else 0.02
    hold_band = 0.03 if is_excess else 0.05

    if signal == "buy":
        return (
            "correct"
            if check_return > threshold
            else ("incorrect" if check_return < -threshold else "neutral")
        )
    elif signal == "sell":
        return (
            "correct"
            if check_return < -threshold
            else ("incorrect" if check_return > threshold else "neutral")
        )
    else:
        return "correct" if abs(check_return) < hold_band else "incorrect"


@router.post("/calibration/resolve")
async def resolve_predictions(x_scheduler_token: str | None = Header(default=None)):
    """
    Resolve pending predictions whose horizon has elapsed.

    Uses split/dividend-adjusted close prices and computes benchmark-relative
    (SPY) returns for proper calibration science. Called via scheduled job.

    Protected by the scheduler token (matches the pattern in routes/
    scheduled.py) — this endpoint was previously unauthenticated with no
    scheduled workflow calling it; both gaps are closed together in this
    change (see Task 7's GitHub Actions wiring).

    After resolution commits, runs the Outcome-Grounded Evaluation Flywheel's
    deterministic promotion policy over the newly-resolved predictions. This
    is best-effort and failure-isolated: a promotion/capture failure never
    rolls back or blocks prediction resolution, which is the pre-existing,
    higher-value contract this endpoint has served since before the
    flywheel existed.
    """
    expected_token = settings.scheduler_secret_token
    if not expected_token:
        raise HTTPException(status_code=503, detail="Scheduler token is not configured")
    if not x_scheduler_token or not compare_digest(x_scheduler_token, expected_token):
        raise HTTPException(status_code=401, detail="Unauthorized scheduler request")

    import asyncio
    from datetime import timedelta

    from src.db import get_pool

    pool = await get_pool()
    newly_resolved: list[dict] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, analysis_id, ticker, signal, confidence, price_at_prediction,
                       horizon_days, created_at, correlation_id
                FROM predictions
                WHERE resolved_at IS NULL
                  AND created_at + (horizon_days || ' days')::interval <= now()
                ORDER BY created_at ASC, id ASC
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
                prediction_date = row["created_at"]
                horizon_days = row["horizon_days"]

                if prediction_price is None or prediction_price <= 0:
                    continue

                resolution_date = prediction_date + timedelta(days=horizon_days)

                try:
                    outcome_price = await asyncio.wait_for(
                        asyncio.to_thread(_fetch_adjusted_price, ticker, resolution_date),
                        timeout=20,
                    )
                except asyncio.TimeoutError:
                    continue
                if outcome_price is None:
                    continue

                try:
                    benchmark_return = await asyncio.wait_for(
                        asyncio.to_thread(
                            _fetch_benchmark_return, prediction_date, resolution_date
                        ),
                        timeout=20,
                    )
                except asyncio.TimeoutError:
                    benchmark_return = None

                realized_return = (outcome_price - prediction_price) / prediction_price
                excess_return = (
                    realized_return - benchmark_return if benchmark_return is not None else None
                )
                check_return = excess_return if excess_return is not None else realized_return
                outcome = _determine_outcome(
                    row["signal"], check_return, is_excess=(excess_return is not None)
                )

                await conn.execute(
                    """
                    UPDATE predictions
                    SET resolved_at = $1, outcome_price = $2, realized_return = $3,
                        outcome = $4, benchmark_return = $5, excess_return = $6,
                        adj_price_at_prediction = $7, adj_outcome_price = $8,
                        resolution_method = 'adjusted_close_benchmark'
                    WHERE id = $9
                    """,
                    datetime.now(timezone.utc),
                    outcome_price,
                    realized_return,
                    outcome,
                    benchmark_return,
                    excess_return,
                    prediction_price,
                    outcome_price,
                    row["id"],
                )
                resolved_count += 1
                newly_resolved.append(
                    {
                        "id": row["id"],
                        "analysis_id": row["analysis_id"],
                        "ticker": ticker,
                        "signal": row["signal"],
                        "confidence": row["confidence"],
                        "outcome": outcome,
                        "realized_return": realized_return,
                        "excess_return": excess_return,
                        "correlation_id": row["correlation_id"],
                    }
                )

    promotion_summary = {"promoted": 0, "excluded": 0, "already_classified": 0, "failed": 0}
    if newly_resolved:
        try:
            from src.eval_flywheel.promotion import promote_resolved_predictions_batch

            summary = await promote_resolved_predictions_batch(newly_resolved)
            promotion_summary = {
                "promoted": summary.promoted,
                "excluded": summary.excluded,
                "already_classified": summary.already_classified,
                "failed": summary.failed,
            }
        except Exception:
            log.warning("eval_flywheel_promotion_batch_failed", exc_info=True)

    return {"resolved_count": resolved_count, "promotion": promotion_summary}


@router.get("/calibration/reliability")
async def get_reliability_diagram():
    """
    Generate data for a reliability diagram (calibration curve).

    Maps predicted probabilities to actual outcomes for proper calibration
    assessment. Shows whether "high confidence" actually means high accuracy.
    """
    rows = await fetch(
        """
        SELECT signal, confidence, outcome, realized_return,
               benchmark_return, excess_return
        FROM predictions
        WHERE resolved_at IS NOT NULL
        ORDER BY created_at DESC
        """
    )

    if not rows:
        return {"status": "insufficient_data", "bins": []}

    # Map confidence to probability bins for reliability diagram
    confidence_to_prob = {"high": 0.80, "medium": 0.55, "low": 0.30}

    # Build reliability data: for each probability bin, what's the actual success rate?
    bins = {}
    for row in rows:
        prob = confidence_to_prob.get(row["confidence"], 0.5)
        if prob not in bins:
            bins[prob] = {
                "predicted_prob": prob,
                "outcomes": [],
                "returns": [],
                "excess_returns": [],
            }
        bins[prob]["outcomes"].append(1.0 if row["outcome"] == "correct" else 0.0)
        if row["realized_return"] is not None:
            bins[prob]["returns"].append(row["realized_return"])
        if row["excess_return"] is not None:
            bins[prob]["excess_returns"].append(row["excess_return"])

    # Compute statistics per bin
    import math

    reliability_bins = []
    for prob, data in sorted(bins.items()):
        n = len(data["outcomes"])
        actual_rate = sum(data["outcomes"]) / n if n > 0 else 0
        # Wilson confidence interval for binomial proportion
        z = 1.96  # 95% CI
        denominator = 1 + z**2 / n
        center = (actual_rate + z**2 / (2 * n)) / denominator
        spread = z * math.sqrt((actual_rate * (1 - actual_rate) + z**2 / (4 * n)) / n) / denominator

        avg_return = sum(data["returns"]) / len(data["returns"]) if data["returns"] else None
        avg_excess = (
            sum(data["excess_returns"]) / len(data["excess_returns"])
            if data["excess_returns"]
            else None
        )

        reliability_bins.append(
            {
                "predicted_probability": prob,
                "actual_success_rate": round(actual_rate, 4),
                "sample_size": n,
                "confidence_interval_95": [
                    round(max(0, center - spread), 4),
                    round(min(1, center + spread), 4),
                ],
                "avg_return": round(avg_return, 4) if avg_return is not None else None,
                "avg_excess_return": round(avg_excess, 4) if avg_excess is not None else None,
                "confidence_label": {0.80: "high", 0.55: "medium", 0.30: "low"}.get(
                    prob, "unknown"
                ),
            }
        )

    # Expected Calibration Error (ECE)
    total_samples = sum(b["sample_size"] for b in reliability_bins)
    ece = (
        sum(
            b["sample_size"]
            / total_samples
            * abs(b["predicted_probability"] - b["actual_success_rate"])
            for b in reliability_bins
        )
        if total_samples > 0
        else None
    )

    # Brier score (proper scoring rule)
    brier_sum = 0.0
    for row in rows:
        prob = confidence_to_prob.get(row["confidence"], 0.5)
        actual = 1.0 if row["outcome"] == "correct" else 0.0
        brier_sum += (prob - actual) ** 2
    brier_score = brier_sum / len(rows) if rows else None

    return {
        "status": "ok",
        "total_resolved": len(rows),
        "reliability_bins": reliability_bins,
        "expected_calibration_error": round(ece, 4) if ece is not None else None,
        "brier_score": round(brier_score, 4) if brier_score is not None else None,
        "methodology": {
            "resolution": "adjusted_close_benchmark",
            "benchmark": "SPY",
            "neutral_band": "2%",
            "confidence_intervals": "Wilson score 95%",
        },
    }
