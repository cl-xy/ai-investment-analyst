"""
Compare node. Generates comparative analysis across multiple tickers.

Takes completed ticker_analyses from state and produces a structured comparison
including relative valuation, normalized metrics, and a brief AI-generated narrative.
"""

import os
from functools import cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from ..state import InvestmentAnalystState


class ComparisonOutput(BaseModel):
    """Structured comparison output."""

    tickers: list[str]
    summary: str = Field(description="1-2 paragraph comparative narrative")
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


@cache
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="openai/gpt-oss-120b",
        temperature=0,
        max_tokens=2048,
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY", ""),
        model_kwargs={"response_format": {"type": "json_object"}},
    )


async def compare_node(state: InvestmentAnalystState) -> dict:
    """Compare all analyzed tickers and produce a structured comparison."""
    analyses = state.get("ticker_analyses", {})

    if len(analyses) < 2:
        return {}

    # Format analyses for the comparison prompt
    analyses_text = []
    for ticker, analysis in analyses.items():
        analyses_text.append(
            f"## {ticker}\n"
            f"Signal: {analysis.get('signal', 'unknown')}\n"
            f"Confidence: {analysis.get('confidence', 'unknown')}\n"
            f"Sentiment: {analysis.get('sentiment_score', 0)}\n"
            f"Risk Flags: {', '.join(analysis.get('risk_flags', []))}\n"
            f"Summary: {analysis.get('news_summary', '')}\n"
        )

    prompt = f"Compare these {len(analyses)} stocks:\n\n" + "\n".join(analyses_text)

    try:
        response = await _get_llm().ainvoke(
            [
                SystemMessage(content=COMPARE_SYSTEM),
                HumanMessage(content=prompt),
            ]
        )

        comparison = ComparisonOutput.model_validate_json(response.content)
        return {"comparison": comparison.model_dump()}
    except (ValidationError, Exception):
        # Non-critical, comparison is supplementary
        return {}
