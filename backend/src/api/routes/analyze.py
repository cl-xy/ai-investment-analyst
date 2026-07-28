"""
Analyze endpoint. Runs the LangGraph agent and persists results to PostgreSQL.
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage

from src.agent.checkpointer import get_checkpointer
from src.agent.concurrency import acquire_analysis_slot, release_analysis_slot
from src.agent.graph import build_graph
from src.api.persistence import persist_full_run
from src.db import fetchrow

from ..schemas import VALID_TICKER_RE, AnalyzeRequest, AnalyzeResponse, TickerAnalysis

router = APIRouter()


async def _run_analysis(tickers: list[str], mcp_tools: dict) -> dict:
    tickers_upper = [t.upper() for t in tickers]
    message = f"Analyze these stocks: {', '.join(tickers_upper)}"

    graph = build_graph(mcp_tools)
    async with get_checkpointer() as checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)
        # Unique thread_id per request to prevent checkpoint state leaking between runs
        thread_id = f"analyze-{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: dict = {
            "messages": [HumanMessage(content=message)],
            "tickers_to_analyze": tickers_upper,
            "intent": "single_ticker" if len(tickers_upper) == 1 else "full_report",
        }
        result = await compiled.ainvoke(initial_state, config=config)
    return result


async def _fetch_cached_analyses(tickers: list[str]) -> dict[str, TickerAnalysis]:
    """Return the most recent stored TickerAnalysis for each ticker.
    Skips insufficient_data results since those represent transient failures."""
    cached: dict[str, TickerAnalysis] = {}
    for ticker in tickers:
        row = await fetchrow(
            """
            SELECT ta.* FROM ticker_analyses ta
            JOIN analyses a ON ta.analysis_id = a.id
            WHERE ta.ticker = $1 AND ta.signal != 'insufficient_data'
            ORDER BY a.created_at DESC
            LIMIT 1
            """,
            ticker,
        )
        if row:
            cached[ticker] = TickerAnalysis(
                ticker=row["ticker"],
                signal=row["signal"],
                confidence=row["confidence"],
                sentiment_score=row["sentiment_score"],
                news_summary=row["news_summary"],
                risk_flags=row["risk_flags"]
                if isinstance(row["risk_flags"], list)
                else json.loads(row["risk_flags"]),
                price_data=row["price_data"]
                if isinstance(row["price_data"], dict)
                else json.loads(row["price_data"]),
                fundamentals=row["fundamentals"]
                if isinstance(row["fundamentals"], dict)
                else json.loads(row["fundamentals"]),
                sec_notes=row["sec_notes"],
            )
    return cached


def _normalise_tickers(raw_tickers: list[str]) -> list[str]:
    seen: set[str] = set()
    tickers: list[str] = []
    for t in raw_tickers:
        normalised = t.upper().strip()
        if normalised and normalised not in seen:
            seen.add(normalised)
            tickers.append(normalised)
    return tickers


async def analyze_tickers(
    tickers: list[str], mcp_tools: dict, *, force_refresh: bool = False
) -> AnalyzeResponse:
    normalised_tickers = _normalise_tickers(tickers)

    if not normalised_tickers:
        raise HTTPException(status_code=400, detail="At least one ticker is required")

    cached_analyses: dict[str, TickerAnalysis] = {}
    new_tickers = normalised_tickers
    if not force_refresh:
        cached_analyses = await _fetch_cached_analyses(normalised_tickers)
        new_tickers = [t for t in normalised_tickers if t not in cached_analyses]

    analyses: dict[str, TickerAnalysis] = dict(cached_analyses)
    report_markdown = ""
    raw_analyses: dict = {}

    if new_tickers:
        try:
            result = await _run_analysis(new_tickers, mcp_tools)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc

        raw_analyses: dict = result.get("ticker_analyses", {})
        for ticker, data in raw_analyses.items():
            analyses[ticker] = TickerAnalysis(
                ticker=data.get("ticker", ticker),
                signal=data.get("signal", "insufficient_data"),
                confidence=data.get("confidence", "low"),
                sentiment_score=float(data.get("sentiment_score", 0.0)),
                news_summary=data.get("news_summary", ""),
                risk_flags=data.get("risk_flags", []),
                price_data=data.get("price_data", {}),
                fundamentals=data.get("fundamentals", {}),
                sec_notes=data.get("sec_notes", ""),
            )
        report_markdown = result.get("report_markdown", "")

    # Persist to PostgreSQL with debate fields + predictions
    raw_for_persist = {}
    for ticker, ta in analyses.items():
        if ticker not in new_tickers and ticker in cached_analyses:
            continue
        if new_tickers and ticker in raw_analyses:
            raw_for_persist[ticker] = raw_analyses[ticker]
        else:
            dumped = ta.model_dump(
                include={"ticker", "signal", "confidence", "sentiment_score",
                         "news_summary", "risk_flags", "price_data", "fundamentals", "sec_notes"}
            )
            dumped.setdefault("thesis", "")
            dumped.setdefault("bull_case", [])
            dumped.setdefault("bear_case", [])
            raw_for_persist[ticker] = dumped

    created_at = datetime.now(timezone.utc)

    try:
        analysis_id = await persist_full_run(
            normalised_tickers, raw_for_persist, report_markdown
        )
    except Exception:
        # Persistence failure should not block the response; the analysis
        # itself succeeded. Use a generated id so the client still gets a
        # valid response shape.
        analysis_id = uuid.uuid4()

    return AnalyzeResponse(
        id=str(analysis_id),
        tickers=normalised_tickers,
        report_markdown=report_markdown,
        analyses=analyses,
        created_at=created_at,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: Request, body: AnalyzeRequest) -> AnalyzeResponse:
    mcp_tools = request.app.state.mcp_tools

    # Validate tickers (same rules as streaming endpoint)
    normalised = _normalise_tickers(body.tickers)
    if not normalised:
        raise HTTPException(status_code=400, detail="At least one valid ticker is required")
    if len(normalised) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 tickers per request")
    invalid = [t for t in normalised if not VALID_TICKER_RE.match(t)]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker symbols: {', '.join(invalid)}",
        )

    # Respect global concurrency limit
    acquired = await acquire_analysis_slot()
    if not acquired:
        raise HTTPException(
            status_code=503,
            detail="Analysis capacity reached. Please try again shortly.",
        )
    try:
        return await analyze_tickers(normalised, mcp_tools, force_refresh=False)
    finally:
        release_analysis_slot()
