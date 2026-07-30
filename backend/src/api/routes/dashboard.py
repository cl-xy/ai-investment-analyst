"""
Dashboard routes. List and retrieve persisted analysis results.
"""

import uuid

from fastapi import APIRouter, HTTPException

from src.db import execute, fetch, fetchrow

from ..schemas import AnalysisListItem, AnalyzeResponse, TickerAnalysis

router = APIRouter()


@router.get("/dashboard", response_model=list[AnalysisListItem])
async def list_analyses() -> list[AnalysisListItem]:
    rows = await fetch("SELECT id, tickers, created_at FROM analyses ORDER BY created_at DESC")
    return [
        AnalysisListItem(
            id=str(row["id"]),
            tickers=row["tickers"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.get("/dashboard/{analysis_id}", response_model=AnalyzeResponse)
async def get_analysis(analysis_id: str) -> AnalyzeResponse:
    try:
        aid = uuid.UUID(analysis_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    row = await fetchrow("SELECT * FROM analyses WHERE id = $1", aid)
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    ticker_rows = await fetch("SELECT * FROM ticker_analyses WHERE analysis_id = $1", aid)

    analyses = {}
    for tr in ticker_rows:
        analyses[tr["ticker"]] = TickerAnalysis(
            ticker=tr["ticker"],
            signal=tr["signal"],
            confidence=tr["confidence"],
            sentiment_score=tr["sentiment_score"],
            news_summary=tr["news_summary"],
            risk_flags=tr["risk_flags"],
            price_data=tr["price_data"],
            fundamentals=tr["fundamentals"],
            earnings=tr["earnings"],
            sec_notes=tr["sec_notes"],
        )

    return AnalyzeResponse(
        id=str(row["id"]),
        tickers=row["tickers"],
        report_markdown=row["report_markdown"],
        analyses=analyses,
        created_at=row["created_at"],
    )


@router.delete("/dashboard/{analysis_id}", status_code=204)
async def delete_analysis(analysis_id: str) -> None:
    """
    Delete an analysis. Protected by DemoAuthMiddleware (same as other
    user-facing endpoints under /api/dashboard).
    """
    try:
        aid = uuid.UUID(analysis_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    result = await execute("DELETE FROM analyses WHERE id = $1", aid)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Analysis not found")
