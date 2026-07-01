import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load env before LangChain imports resolve API keys
load_dotenv()

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.agent.graph import build_graph
from src.agent.mcp_client import create_mcp_client

from ..db import get_collection
from ..schemas import AnalyzeRequest, AnalyzeResponse, TickerAnalysis

router = APIRouter()

_DEFAULT_THREAD = "api-session"


async def _run_analysis(tickers: list[str]) -> dict:
    Path("data").mkdir(exist_ok=True)
    tickers_upper = [t.upper() for t in tickers]
    message = f"Analyze these stocks: {', '.join(tickers_upper)}"

    client = create_mcp_client()
    tools_list = await client.get_tools()
    mcp_tools = {t.name: t for t in tools_list}
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
    """Return the most recent stored TickerAnalysis for each ticker that already exists in the DB."""
    collection = get_collection("analyses")
    cached: dict[str, TickerAnalysis] = {}
    for ticker in tickers:
        doc = await collection.find_one(
            {f"analyses.{ticker}": {"$exists": True}},
            sort=[("created_at", -1)],
        )
        if doc:
            cached[ticker] = TickerAnalysis(**doc["analyses"][ticker])
    return cached


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    # Deduplicate and normalise
    seen: set[str] = set()
    tickers: list[str] = []
    for t in request.tickers:
        normalised = t.upper().strip()
        if normalised and normalised not in seen:
            seen.add(normalised)
            tickers.append(normalised)

    if not tickers:
        raise HTTPException(status_code=400, detail="At least one ticker is required")

    # Separate already-cached tickers from ones that need fresh analysis
    cached_analyses = await _fetch_cached_analyses(tickers)
    new_tickers = [t for t in tickers if t not in cached_analyses]

    analyses: dict[str, TickerAnalysis] = dict(cached_analyses)
    report_markdown = ""

    if new_tickers:
        try:
            result = await _run_analysis(new_tickers)
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

    created_at = datetime.now(timezone.utc)
    doc = {
        "tickers": tickers,
        "report_markdown": report_markdown,
        "analyses": {k: v.model_dump() for k, v in analyses.items()},
        "created_at": created_at,
    }

    collection = get_collection("analyses")
    insert_result = await collection.insert_one(doc)
    record_id = str(insert_result.inserted_id)

    return AnalyzeResponse(
        id=record_id,
        tickers=tickers,
        report_markdown=report_markdown,
        analyses=analyses,
        created_at=created_at,
    )
