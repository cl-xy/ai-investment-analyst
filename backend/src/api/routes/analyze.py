"""
Analyze endpoint. Runs the LangGraph agent and persists results to PostgreSQL.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.agent.graph import build_graph

from ..db import execute, fetchrow
from ..schemas import AnalyzeRequest, AnalyzeResponse, TickerAnalysis

router = APIRouter()

_DEFAULT_THREAD = "api-session"


async def _run_analysis(tickers: list[str], mcp_tools: dict) -> dict:
    Path("data").mkdir(exist_ok=True)
    tickers_upper = [t.upper() for t in tickers]
    message = f"Analyze these stocks: {', '.join(tickers_upper)}"

    graph = build_graph(mcp_tools)
    async with AsyncSqliteSaver.from_conn_string("data/checkpointer.db") as checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": _DEFAULT_THREAD}}
        initial_state: dict = {
            "messages": [HumanMessage(content=message)],
            "tickers_to_analyze": tickers_upper,
        }
        result = await compiled.ainvoke(initial_state, config=config)
    return result


async def _fetch_cached_analyses(tickers: list[str]) -> dict[str, TickerAnalysis]:
    """Return the most recent stored TickerAnalysis for each ticker."""
    cached: dict[str, TickerAnalysis] = {}
    for ticker in tickers:
        row = await fetchrow(
            """
            SELECT ta.* FROM ticker_analyses ta
            JOIN analyses a ON ta.analysis_id = a.id
            WHERE ta.ticker = $1
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


async def analyze_tickers(tickers: list[str], mcp_tools: dict, *, force_refresh: bool = False) -> AnalyzeResponse:
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

    # Persist to PostgreSQL
    created_at = datetime.now(timezone.utc)
    row = await fetchrow(
        """
        INSERT INTO analyses (tickers, report_markdown, created_at)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        normalised_tickers,
        report_markdown,
        created_at,
    )
    analysis_id = row["id"]

    # Insert individual ticker analyses
    for ticker, ta in analyses.items():
        await execute(
            """
            INSERT INTO ticker_analyses (
                analysis_id, ticker, signal, confidence, sentiment_score,
                news_summary, risk_flags, price_data, fundamentals, sec_notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            analysis_id,
            ta.ticker,
            ta.signal,
            ta.confidence,
            ta.sentiment_score,
            ta.news_summary,
            json.dumps(ta.risk_flags),
            json.dumps(ta.price_data),
            json.dumps(ta.fundamentals),
            ta.sec_notes,
        )

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
    return await analyze_tickers(body.tickers, mcp_tools, force_refresh=False)
