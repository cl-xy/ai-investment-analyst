"""
Comparison endpoint. Compares 2-3 tickers using existing analyses or running fresh ones.
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request

from src.agent.concurrency import acquire_analysis_slot, release_analysis_slot
from src.api.schemas import VALID_TICKER_RE, CompareResponse
from src.logging_config import get_logger
from src.middleware.auth import limiter

from .analyze import analyze_tickers

log = get_logger("compare")

router = APIRouter()

# Compare must return within Fly.io proxy timeout. The proxy kills non-streaming
# connections after ~60s of idle time, so the app must fail fast before that.
# Each ticker's debate can take 2+ min on free-tier LLMs; if analyses aren't
# cached, this route will likely timeout. The 504 response guides users to
# run individual analyses first (which use SSE streaming, bypassing the limit).
COMPARE_TIMEOUT = 55  # seconds — must be < Fly.io's ~60s proxy idle timeout


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

    # Deduplicate while preserving order
    ticker_list = list(dict.fromkeys(ticker_list))

    if len(ticker_list) < 2:
        raise HTTPException(status_code=400, detail="At least 2 tickers required for comparison")
    if len(ticker_list) > 3:
        raise HTTPException(status_code=400, detail="Maximum 3 tickers for comparison")

    invalid = [t for t in ticker_list if not VALID_TICKER_RE.match(t)]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid ticker symbols: {', '.join(invalid)}")

    # Read mcp_tools BEFORE acquiring the slot so an AttributeError here
    # doesn't leak a concurrency slot (only 3 available globally).
    mcp_tools = request.app.state.mcp_tools

    # Acquire concurrency slot to respect the global 3-slot limit
    slot_acquired = await acquire_analysis_slot()
    if not slot_acquired:
        raise HTTPException(
            status_code=503,
            detail="Server at capacity; try again shortly.",
        )

    # Run analysis with timeout (will use cache if available)
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
                "Free-tier LLM models are slow; run individual analyses first "
                "(streaming bypasses this limit) to populate the cache, then compare."
            ),
        ) from None
    except Exception as exc:
        log.error("compare_analysis_failed", tickers=ticker_list, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail="Analysis failed; try again or run individual analyses first.",
        ) from None
    finally:
        release_analysis_slot()

    return {
        "tickers": ticker_list,
        "analyses": {k: v.model_dump() for k, v in result.analyses.items()},
        "report_markdown": result.report_markdown,
        "comparison": result.comparison,
    }
