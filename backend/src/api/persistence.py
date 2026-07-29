"""
Shared persistence helper for ticker analyses and predictions.

Used by both the streaming and non-streaming analysis paths to avoid divergence.
Handles debate field extraction, price extraction, and prediction recording.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

import asyncpg

from src.db import get_pool

log = logging.getLogger(__name__)


def extract_current_price(price_data: dict) -> float | None:
    """
    Extract the current market price from a ticker's price_data dict.

    Tries fields in priority order based on what yfinance provides.
    Returns None if no price can be determined.
    """
    if not price_data:
        return None

    # Direct price fields (from yfinance quote data)
    for key in ("currentPrice", "regularMarketPrice", "current_price", "price", "close"):
        val = price_data.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue

    # Nested: price_data might have a "quote" sub-dict
    quote = price_data.get("quote", {})
    if isinstance(quote, dict):
        for key in ("currentPrice", "regularMarketPrice", "price", "close"):
            val = quote.get(key)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue

    # Last resort: previousClose
    prev = price_data.get("previousClose") or price_data.get("previous_close")
    if prev is not None:
        try:
            return float(prev)
        except (ValueError, TypeError):
            pass

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

    # Serialize debate record
    debate_json = None
    if debate_data:
        try:
            debate_json = json.dumps(debate_data)
        except (TypeError, ValueError):
            log.warning("Failed to serialize debate record for %s", ticker)

    # Core fields
    signal = analysis.get("signal", "insufficient_data")
    confidence = analysis.get("confidence", "low")
    sentiment_score = float(analysis.get("sentiment_score", 0.0))
    thesis = analysis.get("thesis", "")
    bull_case = analysis.get("bull_case", [])
    bear_case = analysis.get("bear_case", [])
    news_summary = analysis.get("news_summary", "")
    risk_flags = analysis.get("risk_flags", [])
    price_data = analysis.get("price_data", {})
    fundamentals = analysis.get("fundamentals", {})
    earnings = analysis.get("earnings", {})
    sec_notes = analysis.get("sec_notes", "")

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
        json.dumps(bull_case),
        json.dumps(bear_case),
        news_summary,
        json.dumps(risk_flags),
        json.dumps(price_data),
        json.dumps(fundamentals),
        json.dumps(earnings),
        sec_notes,
        debate_json,
        verdict_rationale,
        json.dumps(key_disagreements),
    )


async def _record_prediction(
    conn: asyncpg.Connection,
    analysis_id: uuid.UUID,
    ticker: str,
    analysis: dict,
    horizon_days: int = 30,
) -> uuid.UUID | None:
    """
    Record a prediction for calibration tracking. Uses the provided connection.
    Returns the prediction UUID if recorded, None if skipped.
    """
    signal = analysis.get("signal", "insufficient_data")
    if signal == "insufficient_data":
        return None

    price_data = analysis.get("price_data", {})
    price_at_prediction = extract_current_price(price_data)

    if price_at_prediction is None:
        log.warning("No price available for prediction: %s", ticker)

    pred_id = uuid.uuid4()
    try:
        await conn.execute(
            """
            INSERT INTO predictions (
                id, analysis_id, ticker, signal, confidence,
                sentiment_score, thesis, price_at_prediction, horizon_days
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            pred_id,
            analysis_id,
            ticker,
            signal,
            analysis.get("confidence", "low"),
            float(analysis.get("sentiment_score", 0.0)),
            analysis.get("thesis", ""),
            price_at_prediction,
            horizon_days,
        )
        log.info(
            "prediction_recorded ticker=%s signal=%s price=%s", ticker, signal, price_at_prediction
        )
        return pred_id
    except Exception as e:
        log.warning("Failed to record prediction for %s: %s", ticker, e)
        return None


async def persist_full_run(
    tickers: list[str],
    ticker_analyses: dict[str, dict],
    report_markdown: str = "",
) -> uuid.UUID:
    """
    Persist a complete analysis run: creates the analyses row,
    persists each ticker analysis with debate data, and records predictions.

    All writes are wrapped in a single transaction for consistency.
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
                    await _persist_analysis_with_debate(conn, analysis_id, ticker, analysis)
                    await _record_prediction(conn, analysis_id, ticker, analysis)
                except Exception as e:
                    log.warning("Failed to persist analysis for %s: %s", ticker, e)

    return analysis_id
