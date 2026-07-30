"""
Compare node. Generates comparative analysis across multiple tickers.

Takes completed ticker_analyses from state and produces a structured comparison
including relative valuation, normalized metrics, and a brief AI-generated narrative.
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from src.logging_config import get_logger

from ..json_utils import extract_json
from ..llm_fallback import invoke_with_fallback
from ..state import InvestmentAnalystState

log = get_logger(__name__)


class ComparisonOutput(BaseModel):
    """Structured comparison output."""

    tickers: list[str] = Field(default_factory=list)
    summary: str = Field(default="", description="1-2 paragraph comparative narrative")
    metrics_table: list[dict] = Field(
        default_factory=list,
        description="Normalized metrics for comparison (P/E, growth, sentiment, etc.)",
    )
    relative_ranking: list[dict] = Field(
        default_factory=list, description="Tickers ranked by overall attractiveness with reasoning"
    )
    key_differentiators: list[str] = Field(
        default_factory=list, description="3-5 key differences between the tickers"
    )
    status: str = Field(default="ok", description="'ok' or 'failed'")
    error: str | None = Field(default=None, description="Failure reason when status is 'failed'")


COMPARE_SYSTEM = """You are a professional equity research analyst comparing multiple stocks.
Given the individual analyses below, produce a comparative assessment.

Return ONLY valid JSON matching this schema:
{
    "tickers": ["AAPL", "NVDA"],
    "summary": "1-2 paragraph comparative narrative highlighting relative strengths and weaknesses",
    "metrics_table": [
        {"ticker": "AAPL", "signal": "hold", "confidence": "medium", "sentiment": 0.3, "risk_count": 2},
        {"ticker": "NVDA", "signal": "buy", "confidence": "high", "sentiment": 0.8, "risk_count": 1}
    ],
    "relative_ranking": [
        {"ticker": "NVDA", "rank": 1, "reasoning": "Stronger growth catalysts and higher conviction signal"},
        {"ticker": "AAPL", "rank": 2, "reasoning": "Stable but limited near-term upside"}
    ],
    "key_differentiators": [
        "NVDA has 150% revenue growth vs AAPL's 5%",
        "AAPL has lower risk profile (2 flags vs 3)",
        "Both have strong fundamentals but different growth trajectories"
    ]
}

Be concise, evidence-based, and acknowledge when differences are marginal."""


def _normalize_content(content) -> str:
    """Extract text from LangChain response content (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Join text fields from content blocks
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


async def compare_node(state: InvestmentAnalystState) -> dict:
    """Compare all analyzed tickers and produce a structured comparison."""
    analyses = state.get("ticker_analyses", {})
    correlation_id = state.get("correlation_id")
    _log = log.bind(correlation_id=correlation_id, node="compare") if correlation_id else log

    if len(analyses) < 2:
        return {}

    try:
        # Format analyses for the comparison prompt
        analyses_text = []
        for ticker, analysis in analyses.items():
            # Defensively handle non-dict values or missing keys
            if not isinstance(analysis, dict):
                analysis = analysis.model_dump() if hasattr(analysis, "model_dump") else {}
            risk_flags = analysis.get("risk_flags") or []
            if isinstance(risk_flags, str):
                risk_flags = [risk_flags]
            analyses_text.append(
                f"## {ticker}\n"
                f"Signal: {analysis.get('signal', 'unknown')}\n"
                f"Confidence: {analysis.get('confidence', 'unknown')}\n"
                f"Sentiment: {analysis.get('sentiment_score', 0)}\n"
                f"Risk Flags: {', '.join(str(f) for f in risk_flags)}\n"
                f"Summary: {analysis.get('news_summary', '')}\n"
            )

        prompt = f"Compare these {len(analyses)} stocks:\n\n" + "\n".join(analyses_text)

        response = await invoke_with_fallback(
            [
                SystemMessage(content=COMPARE_SYSTEM),
                HumanMessage(content=prompt),
            ],
            temperature=0,
            max_tokens=8192,
            request_timeout=120,
        )

        content_str = _normalize_content(response.content)

        # Primary path: direct Pydantic JSON validation
        try:
            comparison = ComparisonOutput.model_validate_json(content_str)
        except (ValidationError, json.JSONDecodeError):
            # Fallback: strip markdown fences / preamble via extract_json
            parsed = extract_json(content_str)
            if isinstance(parsed, dict):
                comparison = ComparisonOutput.model_validate(parsed)
            else:
                raise

        return {"comparison": comparison.model_dump()}
    except Exception as e:
        # Non-critical, comparison is supplementary — surface the failure instead
        # of silently dropping it so the API/UI can show "unavailable" rather
        # than nothing at all.
        _log.warning("compare_node_failed", error=str(e), exc_info=True)
        failed = ComparisonOutput(
            tickers=list(analyses.keys()) if analyses else [],
            status="failed",
            error=str(e)[:200],
        )
        return {"comparison": failed.model_dump()}
