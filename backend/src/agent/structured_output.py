"""
Pydantic schemas for structured LLM outputs.

Replaces brittle extract_json() with JSON mode + Pydantic validation.
Single retry on validation failure. Sends errors back to the model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Links a claim in the analysis to a specific data source."""

    source_id: str = Field(
        description="References a tool_result source_id (e.g. 'yfinance:NVDA:1706140800')"
    )
    claim: str = Field(description="The specific claim being cited")
    provider: str = Field(description="Data provider: yfinance, newsapi, sec_edgar, rss")


class AnalysisOutput(BaseModel):
    """Structured output from the analysis node. Validated via Pydantic."""

    ticker: str
    signal: Literal["buy", "hold", "sell", "insufficient_data"]
    confidence: Literal["high", "medium", "low"]
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    thesis: str = Field(description="2-3 sentence investment thesis")
    bull_case: list[str] = Field(default_factory=list, description="2-4 bullish arguments")
    bear_case: list[str] = Field(default_factory=list, description="2-4 bearish arguments")
    risk_flags: list[str] = Field(default_factory=list, description="Key risks (0-5)")
    citations: list[Citation] = Field(default_factory=list, description="Source provenance chain")
    data_gaps: list[str] = Field(default_factory=list, description="What data was unavailable")
    price_data: dict = Field(default_factory=dict)
    fundamentals: dict = Field(default_factory=dict)
    sec_notes: str = ""
    news_summary: str = ""


class RouterOutput(BaseModel):
    """Structured output from the router node."""

    intent: Literal[
        "full_report",
        "single_ticker",
        "add_position",
        "remove_position",
        "list_portfolio",
        "conversational",
    ]
    tickers: list[str] = Field(default_factory=list)
    reasoning: str = Field(default="", description="Brief explanation of classification")
