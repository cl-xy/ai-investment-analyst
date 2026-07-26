"""
Comparison endpoint. Compares 2-3 tickers using existing analyses or running fresh ones.
"""

from fastapi import APIRouter, HTTPException, Query

from .analyze import analyze_tickers

router = APIRouter()


@router.get("/compare")
async def compare_tickers(
    tickers: str = Query(..., description="Comma-separated tickers (2-3)"),
):
    """
    Compare 2-3 tickers. Runs analysis if needed, then generates comparison.
    Returns both individual analyses and the comparative assessment.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

    if len(ticker_list) < 2:
        raise HTTPException(status_code=400, detail="At least 2 tickers required for comparison")
    if len(ticker_list) > 3:
        raise HTTPException(status_code=400, detail="Maximum 3 tickers for comparison")

    # Run analysis (will use cache if available)
    result = await analyze_tickers(ticker_list, force_refresh=False)

    return {
        "tickers": ticker_list,
        "analyses": {k: v.model_dump() for k, v in result.analyses.items()},
        "report_markdown": result.report_markdown,
    }
