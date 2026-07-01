"""
Dashboard routes — list and retrieve persisted analysis results from MongoDB.
"""

from bson import ObjectId
from fastapi import APIRouter, HTTPException

from ..db import get_collection
from ..schemas import AnalysisListItem, AnalyzeResponse, TickerAnalysis

router = APIRouter()


def _doc_to_response(doc: dict) -> AnalyzeResponse:
    analyses = {
        ticker: TickerAnalysis(**data)
        for ticker, data in doc.get("analyses", {}).items()
    }
    return AnalyzeResponse(
        id=str(doc["_id"]),
        tickers=doc["tickers"],
        report_markdown=doc.get("report_markdown", ""),
        analyses=analyses,
        created_at=doc["created_at"],
    )


@router.get("/dashboard", response_model=list[AnalysisListItem])
async def list_analyses() -> list[AnalysisListItem]:
    collection = get_collection("analyses")
    cursor = collection.find({}, {"tickers": 1, "created_at": 1}).sort("created_at", -1)
    items = []
    async for doc in cursor:
        items.append(AnalysisListItem(
            id=str(doc["_id"]),
            tickers=doc["tickers"],
            created_at=doc["created_at"],
        ))
    return items


@router.get("/dashboard/{analysis_id}", response_model=AnalyzeResponse)
async def get_analysis(analysis_id: str) -> AnalyzeResponse:
    try:
        oid = ObjectId(analysis_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    collection = get_collection("analyses")
    doc = await collection.find_one({"_id": oid})
    if doc is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return _doc_to_response(doc)


@router.delete("/dashboard/{analysis_id}", status_code=204)
async def delete_analysis(analysis_id: str) -> None:
    try:
        oid = ObjectId(analysis_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    collection = get_collection("analyses")
    result = await collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Analysis not found")
