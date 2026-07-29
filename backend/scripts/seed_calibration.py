"""
Seed script for demo calibration data.

Populates the predictions table with realistic-looking historical predictions
so the Track Record page has data to display during demos.

Run: cd backend && .venv/bin/python -m scripts.seed_calibration
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from src.db import execute, get_pool, init_schema

# Realistic demo predictions: mix of correct, incorrect, and pending
SEED_PREDICTIONS = [
    # Resolved predictions (30+ days old, with outcomes)
    {"ticker": "NVDA", "signal": "buy", "confidence": "high", "thesis": "AI infrastructure spending accelerating, data center revenue growing 150%+ YoY with no signs of deceleration", "price": 125.40, "return": 0.18, "outcome": "correct", "days_ago": 65},
    {"ticker": "AAPL", "signal": "hold", "confidence": "medium", "thesis": "iPhone cycle maturing, services growth steady but hardware margins under pressure from component costs", "price": 198.50, "return": 0.03, "outcome": "correct", "days_ago": 58},
    {"ticker": "TSLA", "signal": "sell", "confidence": "high", "thesis": "Margin compression from price cuts, increasing competition in China, FSD timeline uncertainty", "price": 245.80, "return": -0.12, "outcome": "correct", "days_ago": 52},
    {"ticker": "MSFT", "signal": "buy", "confidence": "high", "thesis": "Azure growth reaccelerating on AI workloads, Copilot monetization beginning to show in enterprise", "price": 420.30, "return": 0.08, "outcome": "correct", "days_ago": 48},
    {"ticker": "META", "signal": "buy", "confidence": "medium", "thesis": "Ad revenue recovery strong, Reels monetization gap closing, efficiency year paying dividends", "price": 485.20, "return": 0.11, "outcome": "correct", "days_ago": 45},
    {"ticker": "AMD", "signal": "buy", "confidence": "high", "thesis": "MI300 gaining data center traction, server CPU share gains continuing against Intel", "price": 155.60, "return": -0.05, "outcome": "incorrect", "days_ago": 62},
    {"ticker": "GOOGL", "signal": "hold", "confidence": "low", "thesis": "Search moat questioned by AI assistants, but cloud growth and YouTube shorts offset near-term", "price": 175.90, "return": 0.09, "outcome": "incorrect", "days_ago": 55},
    {"ticker": "AMZN", "signal": "buy", "confidence": "medium", "thesis": "AWS reacceleration confirmed, retail margins expanding, advertising high-margin and growing 20%+", "price": 185.40, "return": 0.14, "outcome": "correct", "days_ago": 50},
    {"ticker": "NFLX", "signal": "hold", "confidence": "medium", "thesis": "Ad tier gaining traction but ARPU pressure, password sharing crackdown boost is one-time", "price": 625.80, "return": 0.06, "outcome": "correct", "days_ago": 44},
    {"ticker": "JPM", "signal": "buy", "confidence": "low", "thesis": "Net interest income benefiting from rate environment, but credit losses ticking up in consumer", "price": 198.60, "return": -0.03, "outcome": "incorrect", "days_ago": 60},
    {"ticker": "COST", "signal": "hold", "confidence": "high", "thesis": "Membership model resilient but valuation stretched at 50x, limited upside at current multiples", "price": 890.40, "return": 0.02, "outcome": "correct", "days_ago": 42},
    {"ticker": "CRM", "signal": "sell", "confidence": "medium", "thesis": "Enterprise AI spending shifting to platform plays, Salesforce growth decelerating to mid-teens", "price": 265.30, "return": 0.08, "outcome": "incorrect", "days_ago": 56},

    # Unresolved predictions (< 30 days old, still pending)
    {"ticker": "NVDA", "signal": "buy", "confidence": "high", "thesis": "Blackwell ramp exceeding expectations, hyperscaler capex commitments through 2027 provide multi-year visibility", "price": 148.20, "return": None, "outcome": None, "days_ago": 12},
    {"ticker": "TSLA", "signal": "hold", "confidence": "medium", "thesis": "Robotaxi narrative gaining steam but execution risk high, energy storage a bright spot", "price": 262.40, "return": None, "outcome": None, "days_ago": 8},
    {"ticker": "AAPL", "signal": "buy", "confidence": "medium", "thesis": "Apple Intelligence driving upgrade cycle, Vision Pro enterprise adoption starting", "price": 215.80, "return": None, "outcome": None, "days_ago": 15},
    {"ticker": "SPY", "signal": "hold", "confidence": "low", "thesis": "Breadth narrowing but earnings growth broadening, Fed cuts priced in", "price": 558.90, "return": None, "outcome": None, "days_ago": 5},
    {"ticker": "MSFT", "signal": "buy", "confidence": "medium", "thesis": "Copilot enterprise penetration accelerating, Azure AI capacity constraints easing", "price": 452.60, "return": None, "outcome": None, "days_ago": 18},
    {"ticker": "AMD", "signal": "buy", "confidence": "medium", "thesis": "MI350 competitive with Blackwell on inference workloads, enterprise pipeline building", "price": 148.90, "return": None, "outcome": None, "days_ago": 10},
]


async def seed():
    """Insert demo predictions into the database."""
    await init_schema()

    # Check if seed data already exists (idempotent)
    pool = await get_pool()
    count = await pool.fetchval("SELECT COUNT(*) FROM predictions WHERE thesis LIKE '%demo seed%'")
    if count and count > 0:
        print(f"Seed data already exists ({count} rows). Skipping.")
        return

    now = datetime.now(timezone.utc)

    for pred in SEED_PREDICTIONS:
        pred_id = uuid.uuid4()
        created_at = now - timedelta(days=pred["days_ago"])
        resolved_at = (created_at + timedelta(days=30)) if pred["outcome"] else None
        outcome_price = pred["price"] * (1 + pred["return"]) if pred["return"] is not None else None

        await execute(
            """
            INSERT INTO predictions (
                id, ticker, signal, confidence, sentiment_score, thesis,
                price_at_prediction, horizon_days, created_at,
                resolved_at, outcome_price, realized_return, outcome
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            pred_id,
            pred["ticker"],
            pred["signal"],
            pred["confidence"],
            0.5 if pred["signal"] == "buy" else (-0.3 if pred["signal"] == "sell" else 0.0),
            pred["thesis"],
            pred["price"],
            30,
            created_at,
            resolved_at,
            outcome_price,
            pred["return"],
            pred["outcome"],
        )

    print(f"Seeded {len(SEED_PREDICTIONS)} predictions ({sum(1 for p in SEED_PREDICTIONS if p['outcome'])} resolved, {sum(1 for p in SEED_PREDICTIONS if not p['outcome'])} pending)")


if __name__ == "__main__":
    asyncio.run(seed())
