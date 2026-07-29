"""
Comparison endpoint. Compares 2-3 tickers using existing analyses or running fresh ones.
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas import VALID_TICKER_RE, CompareResponse
from src.middleware.auth import limiter

from .analyze import analyze_tickers

router = APIRouter()

# Compare must return within HTTP timeout. Each ticker's debate can take 2+ min
# on free-tier LLMs, so cap total wall time at 90s (Fly.io proxy timeout is 60s
# for non-streaming, but we set a generous internal cap and let the proxy kill
# truly stuck requests).
COMPARE_TIMEOUT = 90  # seconds


@router.get("/compare", response_model=CompareResponse)
@limiter.limit("10/minute")
async def compare_tickers(
    request: Request,
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

    invalid = [t for t in ticker_list if not VALID_TICKER_RE.match(t)]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid ticker symbols: {', '.join(invalid)}")

    # Run analysis with timeout (will use cache if available)
    mcp_tools = request.app.state.mcp_tools
    try:
        result = await asyncio.wait_for(
            analyze_tickers(ticker_list, mcp_tools, force_refresh=False),
            timeout=COMPARE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=(
                f"Comparison timed out after {COMPARE_TIMEOUT}s. "
                "Try again later when models are less congested, "
                "or run individual analyses first to populate the cache."
            ),
        )

    return {
        "tickers": ticker_list,
        "analyses": {k: v.model_dump() for k, v in result.analyses.items()},
        "report_markdown": result.report_markdown,
        "comparison": result.comparison,
    }
