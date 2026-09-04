#!/usr/bin/env python3
"""
Seed historical calibration data for the track record page.

Inserts realistic resolved predictions spanning Jan-Jun 2026.
Idempotent: safe to run multiple times.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import asyncpg
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Prediction data: 45 predictions across 10 tickers, Jan-Jun 2026
# Story: tech rally Jan-Feb, pullback March, sideways April, recovery May-Jun
# ---------------------------------------------------------------------------

PREDICTIONS = [
    # --- January 2026: Strong start, AI momentum ---
    {
        "ticker": "NVDA",
        "signal": "buy",
        "confidence": "high",
        "sentiment_score": 0.82,
        "thesis": "Data center revenue acceleration continues to outpace expectations. H100/H200 demand backlog extends through 2026. Gross margins expanding on mix shift toward enterprise inference workloads.",
        "price_at_prediction": 820.0,
        "outcome_price": 905.0,
        "created_at": datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "MSFT",
        "signal": "buy",
        "confidence": "high",
        "sentiment_score": 0.75,
        "thesis": "Azure AI revenue run-rate approaching $15B annually. Copilot enterprise adoption inflecting with 40% QoQ seat growth. Cloud margins expanding as AI workloads scale.",
        "price_at_prediction": 425.0,
        "outcome_price": 452.0,
        "created_at": datetime(2026, 1, 16, 10, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "AAPL",
        "signal": "hold",
        "confidence": "medium",
        "sentiment_score": 0.52,
        "thesis": "iPhone 17 cycle anticipated but Services growth moderating. Valuation stretched at 32x forward. Wait for clearer catalyst from WWDC AI announcements.",
        "price_at_prediction": 225.0,
        "outcome_price": 231.0,
        "created_at": datetime(2026, 1, 18, 9, 45, tzinfo=timezone.utc),
    },
    {
        "ticker": "TSLA",
        "signal": "sell",
        "confidence": "medium",
        "sentiment_score": -0.35,
        "thesis": "Delivery growth decelerating quarter-over-quarter. Margin pressure from price cuts in China not offset by volume. FSD revenue recognition timeline remains uncertain.",
        "price_at_prediction": 280.0,
        "outcome_price": 315.0,  # WRONG: rallied on robotaxi hype
        "created_at": datetime(2026, 1, 20, 11, 15, tzinfo=timezone.utc),
    },
    {
        "ticker": "META",
        "signal": "buy",
        "confidence": "high",
        "sentiment_score": 0.78,
        "thesis": "Reels monetization gap closing faster than expected. AI-driven ad targeting improvements lifting ARPU across all geos. Reality Labs losses narrowing with Quest 4 pre-orders strong.",
        "price_at_prediction": 540.0,
        "outcome_price": 588.0,
        "created_at": datetime(2026, 1, 22, 13, 0, tzinfo=timezone.utc),
    },
    # --- Late January / Early February ---
    {
        "ticker": "AMD",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.61,
        "thesis": "MI300X gaining traction in inference workloads. Server CPU share gains accelerating with Zen 5. Embedded segment bottoming after inventory correction.",
        "price_at_prediction": 165.0,
        "outcome_price": 158.0,  # WRONG: CUDA moat held, MI300 ramp slower than expected
        "created_at": datetime(2026, 1, 28, 10, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "GOOGL",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.58,
        "thesis": "Search AI Overview monetization showing early traction. Cloud growth re-accelerating to 30%+ with Gemini enterprise deals. YouTube Shorts ad load increasing without engagement hit.",
        "price_at_prediction": 185.0,
        "outcome_price": 180.0,  # WRONG: antitrust headlines spooked market
        "created_at": datetime(2026, 1, 30, 14, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "AMZN",
        "signal": "buy",
        "confidence": "high",
        "sentiment_score": 0.72,
        "thesis": "AWS re-acceleration driven by generative AI workloads. Retail margins at all-time highs from automation and advertising growth. Prime Video ad tier exceeding subscriber targets.",
        "price_at_prediction": 210.0,
        "outcome_price": 205.0,  # WRONG: FTC antitrust probe dampened sentiment
        "created_at": datetime(2026, 2, 3, 11, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "NFLX",
        "signal": "hold",
        "confidence": "low",
        "sentiment_score": 0.42,
        "thesis": "Ad tier growth strong but password sharing crackdown tailwinds fading. Content spend increasing for live sports rights. Valuation at 35x feels fair, not compelling either direction.",
        "price_at_prediction": 720.0,
        "outcome_price": 790.0,  # WRONG: live sports drove massive re-rating
        "created_at": datetime(2026, 2, 5, 9, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "JPM",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.55,
        "thesis": "Net interest income benefiting from higher-for-longer rate environment. Trading revenues elevated on volatility. Credit quality stable with consumer delinquencies below pre-COVID norms.",
        "price_at_prediction": 215.0,
        "outcome_price": 222.0,
        "created_at": datetime(2026, 2, 7, 10, 15, tzinfo=timezone.utc),
    },
    # --- February: Continued momentum ---
    {
        "ticker": "NVDA",
        "signal": "buy",
        "confidence": "high",
        "sentiment_score": 0.88,
        "thesis": "Blackwell ramp on track for Q2 volume shipments. Hyperscaler capex guides all revised upward. Networking revenue (Spectrum-X) emerging as meaningful growth vector.",
        "price_at_prediction": 880.0,
        "outcome_price": 940.0,
        "created_at": datetime(2026, 2, 12, 14, 45, tzinfo=timezone.utc),
    },
    {
        "ticker": "TSLA",
        "signal": "buy",
        "confidence": "low",
        "sentiment_score": 0.38,
        "thesis": "Robotaxi unveil creating narrative shift. Energy storage deployments doubling YoY. Risk/reward improving after 15% pullback from highs, though execution risk remains elevated.",
        "price_at_prediction": 265.0,
        "outcome_price": 278.0,  # Correct: modest recovery on energy storage hype
        "created_at": datetime(2026, 2, 14, 10, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "AAPL",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.62,
        "thesis": "Apple Intelligence driving upgrade cycle earlier than expected. Services hitting $100B annual run-rate. India manufacturing expansion reducing geopolitical risk premium.",
        "price_at_prediction": 232.0,
        "outcome_price": 224.0,  # WRONG: China tariff escalation hit supply chain sentiment
        "created_at": datetime(2026, 2, 18, 11, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "META",
        "signal": "hold",
        "confidence": "medium",
        "sentiment_score": 0.48,
        "thesis": "Strong execution priced in at 28x forward. EU regulatory headwinds from Digital Markets Act enforcement could pressure European revenue. Waiting for clearer risk/reward.",
        "price_at_prediction": 575.0,
        "outcome_price": 560.0,
        "created_at": datetime(2026, 2, 20, 13, 15, tzinfo=timezone.utc),
    },
    {
        "ticker": "AMD",
        "signal": "hold",
        "confidence": "low",
        "sentiment_score": 0.44,
        "thesis": "MI300 momentum encouraging but CUDA ecosystem moat limits near-term TAM capture. Valuation requires flawless execution on datacenter GPU roadmap. Prefer to wait for Q1 earnings clarity.",
        "price_at_prediction": 175.0,
        "outcome_price": 162.0,
        "created_at": datetime(2026, 2, 24, 9, 0, tzinfo=timezone.utc),
    },
    # --- March: Pullback / Correction ---
    {
        "ticker": "NVDA",
        "signal": "hold",
        "confidence": "medium",
        "sentiment_score": 0.45,
        "thesis": "Valuation extended after 60% run. Near-term supply constraints could limit upside surprise. Maintaining position but not adding at these levels ahead of earnings.",
        "price_at_prediction": 935.0,
        "outcome_price": 880.0,
        "created_at": datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "MSFT",
        "signal": "hold",
        "confidence": "medium",
        "sentiment_score": 0.50,
        "thesis": "Azure growth strong but Copilot monetization slower than bull case. Trading at premium to historical range. Position sizing appropriate, no action needed.",
        "price_at_prediction": 455.0,
        "outcome_price": 438.0,
        "created_at": datetime(2026, 3, 5, 11, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "GOOGL",
        "signal": "sell",
        "confidence": "medium",
        "sentiment_score": -0.42,
        "thesis": "DOJ antitrust remedy risk underpriced. Search market share erosion from AI chatbots accelerating. Cloud growth not sufficient to offset core search deceleration at current multiple.",
        "price_at_prediction": 192.0,
        "outcome_price": 178.0,
        "created_at": datetime(2026, 3, 7, 14, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "TSLA",
        "signal": "sell",
        "confidence": "high",
        "sentiment_score": -0.65,
        "thesis": "Q1 deliveries tracking well below consensus. European market share declining as legacy OEVs compete on price. Robotaxi timeline pushed again, eroding narrative premium.",
        "price_at_prediction": 310.0,
        "outcome_price": 275.0,
        "created_at": datetime(2026, 3, 10, 10, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "AMZN",
        "signal": "hold",
        "confidence": "low",
        "sentiment_score": 0.40,
        "thesis": "AWS growth solid but retail showing signs of consumer spending fatigue. Advertising growth decelerating from peak. Mixed signals suggest range-bound near term.",
        "price_at_prediction": 225.0,
        "outcome_price": 218.0,
        "created_at": datetime(2026, 3, 12, 9, 45, tzinfo=timezone.utc),
    },
    {
        "ticker": "NFLX",
        "signal": "sell",
        "confidence": "medium",
        "sentiment_score": -0.38,
        "thesis": "Subscriber growth inflection behind us. Content cost inflation returning as competitors exit and talent leverage increases. Macro slowdown could pressure discretionary entertainment spend.",
        "price_at_prediction": 745.0,
        "outcome_price": 702.0,
        "created_at": datetime(2026, 3, 14, 13, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "JPM",
        "signal": "sell",
        "confidence": "low",
        "sentiment_score": -0.28,
        "thesis": "Yield curve normalization headwind for NII. CRE exposure concerns resurfacing. Bank stock rally looks extended relative to earnings growth trajectory.",
        "price_at_prediction": 228.0,
        "outcome_price": 235.0,  # WRONG: IPO market reopening lifted investment banking fees
        "created_at": datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "META",
        "signal": "sell",
        "confidence": "medium",
        "sentiment_score": -0.45,
        "thesis": "Capex guidance raised again for AI infrastructure. Market losing patience with spending pace absent clear near-term ROI. WhatsApp Business monetization delayed to 2027.",
        "price_at_prediction": 555.0,
        "outcome_price": 520.0,
        "created_at": datetime(2026, 3, 19, 11, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "AAPL",
        "signal": "hold",
        "confidence": "high",
        "sentiment_score": 0.50,
        "thesis": "Defensive positioning in risk-off environment. Services recurring revenue provides floor. Not adding given macro uncertainty but no reason to reduce core holding.",
        "price_at_prediction": 228.0,
        "outcome_price": 225.0,
        "created_at": datetime(2026, 3, 21, 14, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "AMD",
        "signal": "sell",
        "confidence": "medium",
        "sentiment_score": -0.52,
        "thesis": "PC/gaming segment still declining. Server GPU ramp slower than guided. Inventory build at channel partners suggests demand pull-forward exhausted. Risk to Q1 guide.",
        "price_at_prediction": 170.0,
        "outcome_price": 152.0,
        "created_at": datetime(2026, 3, 25, 10, 15, tzinfo=timezone.utc),
    },
    # --- April: Stabilization ---
    {
        "ticker": "NVDA",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.65,
        "thesis": "Pullback creating opportunity. Blackwell orders confirmed by multiple hyperscalers. Data center TAM expanding with sovereign AI buildouts. Risk/reward attractive after 10% correction.",
        "price_at_prediction": 870.0,
        "outcome_price": 855.0,  # WRONG: export control fears kept a lid on recovery
        "created_at": datetime(2026, 4, 2, 11, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "MSFT",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.60,
        "thesis": "Copilot enterprise pipeline converting faster in Q2. Azure AI consumption model gaining traction with mid-market. Valuation more reasonable after March correction.",
        "price_at_prediction": 435.0,
        "outcome_price": 428.0,  # WRONG: Copilot churn higher than expected, guidance flat
        "created_at": datetime(2026, 4, 4, 9, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "TSLA",
        "signal": "hold",
        "confidence": "low",
        "sentiment_score": 0.35,
        "thesis": "Sentiment washed out after delivery miss. Model refresh cycle approaching. Energy business providing fundamental support but auto margins need to stabilize first.",
        "price_at_prediction": 270.0,
        "outcome_price": 285.0,
        "created_at": datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "GOOGL",
        "signal": "buy",
        "confidence": "low",
        "sentiment_score": 0.42,
        "thesis": "Oversold on antitrust fears. Cloud growth re-accelerating. Gemini Ultra showing strong enterprise adoption. Risk/reward favorable if remedy is behavioral not structural.",
        "price_at_prediction": 175.0,
        "outcome_price": 183.0,  # Correct: relief rally on behavioral remedy ruling
        "created_at": datetime(2026, 4, 10, 13, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "AMZN",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.58,
        "thesis": "AWS backlog at record levels. Same-day delivery expansion driving retail share gains. Advertising approaching $60B run-rate. Multiple expansion warranted as margins normalize higher.",
        "price_at_prediction": 215.0,
        "outcome_price": 232.0,
        "created_at": datetime(2026, 4, 14, 11, 15, tzinfo=timezone.utc),
    },
    {
        "ticker": "JPM",
        "signal": "hold",
        "confidence": "medium",
        "sentiment_score": 0.48,
        "thesis": "First Republic integration accretive ahead of schedule. Credit reserves adequate. Prefer to wait for clearer macro signal before adding to financials exposure.",
        "price_at_prediction": 218.0,
        "outcome_price": 224.0,
        "created_at": datetime(2026, 4, 16, 10, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "NFLX",
        "signal": "buy",
        "confidence": "low",
        "sentiment_score": 0.40,
        "thesis": "Live sports content (NFL Christmas, WWE) driving engagement metrics. Ad tier ARPU exceeding expectations. Contrarian opportunity after sector rotation out of media.",
        "price_at_prediction": 695.0,
        "outcome_price": 718.0,  # Correct: ad tier monetization beat lifted shares
        "created_at": datetime(2026, 4, 18, 14, 0, tzinfo=timezone.utc),
    },
    # --- May: Recovery begins ---
    {
        "ticker": "NVDA",
        "signal": "buy",
        "confidence": "high",
        "sentiment_score": 0.85,
        "thesis": "Earnings beat confirms Blackwell ramp ahead of schedule. Guidance raised for third consecutive quarter. Inference demand creating second growth vector beyond training.",
        "price_at_prediction": 910.0,
        "outcome_price": 965.0,
        "created_at": datetime(2026, 5, 1, 10, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "META",
        "signal": "buy",
        "confidence": "high",
        "sentiment_score": 0.76,
        "thesis": "Llama 4 open-source release driving developer ecosystem growth. Ad revenue per impression up 22% YoY from AI targeting improvements. Threads reaching monetization scale.",
        "price_at_prediction": 530.0,
        "outcome_price": 580.0,
        "created_at": datetime(2026, 5, 5, 11, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "AAPL",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.63,
        "thesis": "WWDC AI announcements expected to catalyze upgrade cycle narrative. Services margins expanding. Buyback providing consistent EPS support regardless of unit growth.",
        "price_at_prediction": 230.0,
        "outcome_price": 242.0,
        "created_at": datetime(2026, 5, 8, 9, 45, tzinfo=timezone.utc),
    },
    {
        "ticker": "AMD",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.58,
        "thesis": "MI350 announcement at Computex generating positive sentiment. Server CPU share gains continuing. Gaming segment showing early signs of recovery with new console cycle.",
        "price_at_prediction": 155.0,
        "outcome_price": 168.0,
        "created_at": datetime(2026, 5, 12, 10, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "TSLA",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.55,
        "thesis": "Model Y refresh driving order backlog recovery. Energy storage margins expanding. Robotaxi pilot in Austin generating real-world data. Sentiment bottomed after Q1 delivery trough.",
        "price_at_prediction": 285.0,
        "outcome_price": 320.0,
        "created_at": datetime(2026, 5, 15, 13, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "GOOGL",
        "signal": "hold",
        "confidence": "medium",
        "sentiment_score": 0.50,
        "thesis": "Cloud momentum strong but antitrust overhang persists. Search revenue proving more resilient than feared. Holding position pending remedy clarity expected in Q3.",
        "price_at_prediction": 183.0,
        "outcome_price": 188.0,
        "created_at": datetime(2026, 5, 19, 11, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "AMZN",
        "signal": "buy",
        "confidence": "high",
        "sentiment_score": 0.80,
        "thesis": "AWS growth re-accelerated to 35% in Q1. Retail operating margins hit 6% for first time. Kuiper satellite constellation beginning revenue contribution. Clear path to $300+ in 12 months.",
        "price_at_prediction": 232.0,
        "outcome_price": 225.0,  # WRONG: profit-taking after earnings despite strong results
        "created_at": datetime(2026, 5, 22, 14, 30, tzinfo=timezone.utc),
    },
    # --- June: Broad recovery ---
    {
        "ticker": "NVDA",
        "signal": "hold",
        "confidence": "medium",
        "sentiment_score": 0.55,
        "thesis": "Position fully sized after May add. Fundamentals strong but short-term overbought on RSI. Trimming small portion to manage position risk ahead of summer seasonality.",
        "price_at_prediction": 955.0,
        "outcome_price": 1010.0,  # WRONG: AI capex supercycle accelerated, should have held full
        "created_at": datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "MSFT",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.64,
        "thesis": "Copilot Studio enabling custom AI agents for enterprise. Azure AI consumption model driving land-and-expand. GitHub Copilot enterprise penetration reaching critical mass.",
        "price_at_prediction": 450.0,
        "outcome_price": 470.0,
        "created_at": datetime(2026, 6, 5, 11, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "JPM",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.57,
        "thesis": "Investment banking pipeline recovering with IPO market reopening. Net interest income guidance raised. Trading desk market share gains from smaller bank exits.",
        "price_at_prediction": 225.0,
        "outcome_price": 238.0,
        "created_at": datetime(2026, 6, 9, 10, 15, tzinfo=timezone.utc),
    },
    {
        "ticker": "NFLX",
        "signal": "hold",
        "confidence": "medium",
        "sentiment_score": 0.50,
        "thesis": "Subscriber growth moderating to steady state. Content pipeline strong for H2 with several tentpole releases. Fair value near current levels, no edge either direction.",
        "price_at_prediction": 725.0,
        "outcome_price": 735.0,
        "created_at": datetime(2026, 6, 12, 13, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "AAPL",
        "signal": "buy",
        "confidence": "high",
        "sentiment_score": 0.74,
        "thesis": "WWDC 2026 AI features exceeding expectations. On-device LLM capabilities driving clear differentiation. Services ecosystem stickiness at all-time high with 1B+ paid subscribers.",
        "price_at_prediction": 238.0,
        "outcome_price": 252.0,
        "created_at": datetime(2026, 6, 16, 9, 30, tzinfo=timezone.utc),
    },
    {
        "ticker": "TSLA",
        "signal": "sell",
        "confidence": "low",
        "sentiment_score": -0.30,
        "thesis": "Rally from lows looks overextended technically. Margin expansion thesis requires volume growth that macro environment may not support. Trimming ahead of potential Q2 miss.",
        "price_at_prediction": 340.0,
        "outcome_price": 355.0,  # WRONG: momentum traders pushed it higher through earnings
        "created_at": datetime(2026, 6, 20, 11, 0, tzinfo=timezone.utc),
    },
    {
        "ticker": "META",
        "signal": "buy",
        "confidence": "medium",
        "sentiment_score": 0.68,
        "thesis": "Threads daily active users crossing 200M. AI-powered content recommendations driving 15% engagement uplift. Capital return program accelerating with $50B buyback authorization.",
        "price_at_prediction": 575.0,
        "outcome_price": 598.0,
        "created_at": datetime(2026, 6, 25, 14, 0, tzinfo=timezone.utc),
    },
]


def determine_outcome(signal: str, price_at: float, outcome_price: float) -> str:
    """Replicate calibration.py resolution logic."""
    realized_return = (outcome_price - price_at) / price_at

    if signal == "buy":
        if realized_return > 0.02:
            return "correct"
        elif realized_return < -0.02:
            return "incorrect"
        else:
            return "neutral"
    elif signal == "sell":
        if realized_return < -0.02:
            return "correct"
        elif realized_return > 0.02:
            return "incorrect"
        else:
            return "neutral"
    else:  # hold
        if abs(realized_return) < 0.05:
            return "correct"
        else:
            return "incorrect"


async def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set in environment")
        sys.exit(1)

    print("Connecting to database...")
    conn = await asyncpg.connect(database_url)

    try:
        # Idempotent: clear previous seed data
        deleted = await conn.execute("DELETE FROM predictions WHERE created_at < '2026-07-01'")
        print(f"Cleared previous seed data: {deleted}")

        # Insert predictions
        inserted = 0
        for pred in PREDICTIONS:
            price_at = pred["price_at_prediction"]
            outcome_price = pred["outcome_price"]
            signal = pred["signal"]
            created_at = pred["created_at"]
            resolved_at = created_at + timedelta(days=30)
            realized_return = (outcome_price - price_at) / price_at
            outcome = determine_outcome(signal, price_at, outcome_price)

            await conn.execute(
                """
                INSERT INTO predictions (
                    id, analysis_id, ticker, signal, confidence, sentiment_score,
                    thesis, price_at_prediction, horizon_days, created_at,
                    resolved_at, outcome_price, realized_return, outcome
                ) VALUES (
                    gen_random_uuid(), NULL, $1, $2, $3, $4,
                    $5, $6, 30, $7,
                    $8, $9, $10, $11
                )
                """,
                pred["ticker"],
                pred["signal"],
                pred["confidence"],
                pred["sentiment_score"],
                pred["thesis"],
                price_at,
                created_at,
                resolved_at,
                outcome_price,
                realized_return,
                outcome,
            )
            inserted += 1
            if inserted % 10 == 0:
                print(f"  Inserted {inserted}/{len(PREDICTIONS)} predictions...")

        print(f"\nDone! Inserted {inserted} predictions.")

        # Print summary stats
        rows = await conn.fetch(
            """
            SELECT outcome, COUNT(*) as cnt
            FROM predictions
            WHERE created_at < '2026-07-01'
            GROUP BY outcome
            """
        )
        print("\nOutcome distribution:")
        for row in rows:
            print(f"  {row['outcome']}: {row['cnt']}")

        total = sum(row["cnt"] for row in rows)
        correct = next((row["cnt"] for row in rows if row["outcome"] == "correct"), 0)
        print(f"\nOverall accuracy: {correct}/{total} = {correct / total:.1%}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
