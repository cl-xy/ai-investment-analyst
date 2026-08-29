"""
Shared persistence helper for ticker analyses and predictions.

Used by both the streaming and non-streaming analysis paths to avoid divergence.
Handles debate field extraction, price extraction, and prediction recording.
"""

import json
import logging
import math
import uuid
from datetime import datetime, timezone

import asyncpg

from src.db import get_pool
from src.numeric import safe_float as _safe_float
from src.numeric import safe_json_dumps as _safe_json_dumps

log = logging.getLogger(__name__)


def extract_current_price(price_data: dict) -> float | None:
    """
    Extract the current market price from a ticker's price_data dict.

    Tries fields in priority order based on what yfinance provides.
    Returns None if no price can be determined (including NaN/Infinity).
    """
    if not isinstance(price_data, dict) or not price_data:
        return None

    def _try_float(val) -> float | None:
        if val is None:
            return None
        try:
            f = float(val)
        except (ValueError, TypeError):
            return None
        return f if math.isfinite(f) else None

    # Direct price fields (from yfinance quote data)
    for key in ("currentPrice", "regularMarketPrice", "current_price", "price", "close"):
        result = _try_float(price_data.get(key))
        if result is not None:
            return result

    # Nested: price_data might have a "quote" sub-dict
    quote = price_data.get("quote", {})
    if isinstance(quote, dict):
        for key in ("currentPrice", "regularMarketPrice", "price", "close"):
            result = _try_float(quote.get(key))
            if result is not None:
                return result

    # Last resort: previousClose (use `is not None` to handle 0.0 correctly)
    prev = price_data.get("previousClose")
    if prev is None:
        prev = price_data.get("previous_close")
    result = _try_float(prev)
    if result is not None:
        return result

    return None


async def _persist_analysis_with_debate(
    conn: asyncpg.Connection,
    analysis_id: uuid.UUID,
    ticker: str,
    analysis: dict,
) -> None:
    """
    Persist a single ticker analysis to the ticker_analyses table,
    including debate fields if present. Uses the provided connection.
    """
    # Extract debate-specific fields (underscore-prefixed from debate node)
    debate_data = analysis.get("_debate")
    verdict_rationale = analysis.get("_verdict_rationale", "")
    key_disagreements = analysis.get("_key_disagreements", [])

    # Serialize debate record (use `is not None` to preserve empty dicts/lists)
    debate_json = None
    if debate_data is not None:
        try:
            debate_json = json.dumps(debate_data, allow_nan=False)
        except (TypeError, ValueError):
            log.warning("Failed to serialize debate record for %s", ticker)

    # Core fields with safe conversions
    signal = analysis.get("signal") or "insufficient_data"
    confidence = analysis.get("confidence") or "low"
    sentiment_score = _safe_float(analysis.get("sentiment_score"), 0.0)
    thesis = analysis.get("thesis") or ""
    bull_case = analysis.get("bull_case", [])
    bear_case = analysis.get("bear_case", [])
    news_summary = analysis.get("news_summary") or ""
    risk_flags = analysis.get("risk_flags", [])
    price_data = analysis.get("price_data", {})
    fundamentals = analysis.get("fundamentals", {})
    earnings = analysis.get("earnings", {})
    sec_notes = analysis.get("sec_notes") or ""

    await conn.execute(
        """
        INSERT INTO ticker_analyses (
            analysis_id, ticker, signal, confidence, sentiment_score,
            thesis, bull_case, bear_case, news_summary, risk_flags,
            price_data, fundamentals, earnings, sec_notes,
            debate, verdict_rationale, key_disagreements
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
        """,
        analysis_id,
        ticker,
        signal,
        confidence,
        sentiment_score,
        thesis,
        _safe_json_dumps(bull_case),
        _safe_json_dumps(bear_case),
        news_summary,
        _safe_json_dumps(risk_flags),
        _safe_json_dumps(price_data),
        _safe_json_dumps(fundamentals),
        _safe_json_dumps(earnings),
        sec_notes,
        debate_json,
        verdict_rationale,
        _safe_json_dumps(key_disagreements),
    )


async def _record_prediction(
    conn: asyncpg.Connection,
    analysis_id: uuid.UUID,
    ticker: str,
    analysis: dict,
    horizon_days: int = 30,
    correlation_id: str | None = None,
) -> uuid.UUID | None:
    """
    Record a prediction for calibration tracking. Uses the provided connection.
    Returns the prediction UUID if recorded, None if skipped.

    Note: Does NOT catch DB exceptions internally. The caller is responsible
    for wrapping in a savepoint if best-effort semantics are needed.
    """
    signal = analysis.get("signal", "insufficient_data")
    if signal == "insufficient_data":
        return None

    price_data = analysis.get("price_data", {})
    price_at_prediction = extract_current_price(price_data)

    if price_at_prediction is None:
        log.warning("No price available for prediction: %s", ticker)

    pred_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO predictions (
            id, analysis_id, ticker, signal, confidence,
            sentiment_score, thesis, price_at_prediction, horizon_days,
            correlation_id
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
        pred_id,
        analysis_id,
        ticker,
        signal,
        analysis.get("confidence") or "low",
        _safe_float(analysis.get("sentiment_score"), 0.0),
        analysis.get("thesis") or "",
        price_at_prediction,
        horizon_days,
        correlation_id,
    )
    log.info(
        "prediction_recorded ticker=%s signal=%s price=%s", ticker, signal, price_at_prediction
    )
    return pred_id


async def persist_full_run(
    tickers: list[str],
    ticker_analyses: dict[str, dict],
    report_markdown: str = "",
    correlation_id: str | None = None,
) -> uuid.UUID:
    """
    Persist a complete analysis run: creates the analyses row,
    persists each ticker analysis with debate data, and records predictions.

    Each ticker's work is wrapped in a savepoint so that a failure for one
    ticker does not poison the entire transaction (PostgreSQL aborts the
    transaction on any unhandled error without a savepoint).

    `correlation_id`, when provided (streaming path only), is stored on each
    recorded prediction so the evaluation flywheel can later join back to
    evidence_artifacts/citation_validations for that run.

    Returns the analysis_id.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO analyses (tickers, report_markdown, created_at)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                tickers,
                report_markdown,
                datetime.now(timezone.utc),
            )
            analysis_id = row["id"]

            for ticker, analysis in ticker_analyses.items():
                signal = analysis.get("signal", "insufficient_data")
                if signal == "insufficient_data":
                    continue
                try:
                    # Nested transaction creates a SAVEPOINT; if anything
                    # inside fails, only this savepoint is rolled back.
                    async with conn.transaction():
                        await _persist_analysis_with_debate(conn, analysis_id, ticker, analysis)
                        await _record_prediction(
                            conn, analysis_id, ticker, analysis, correlation_id=correlation_id
                        )
                except Exception as e:
                    log.warning("Failed to persist analysis for %s: %s", ticker, e)

    return analysis_id
