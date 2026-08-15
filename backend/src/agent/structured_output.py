"""
Pydantic schemas for structured LLM outputs.

Replaces brittle extract_json() with JSON mode + Pydantic validation.
Single retry on validation failure. Sends errors back to the model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _normalize_literal(v: object) -> object:
    """Lowercase string values before Literal matching (LLMs emit 'Buy', 'HIGH', etc.)."""
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _normalize_ticker(v: str) -> str:
    """Strip whitespace, remove leading '$', uppercase for consistent lookups."""
    return v.strip().lstrip("$").upper()


class Citation(BaseModel):
    """Links a claim in the analysis to a specific data source."""

    source_id: str = Field(
        description="References an evidence artifact ID (e.g. 'ev_abc123def456ab')"
    )
    claim: str = Field(description="The specific claim being cited")
    provider: Literal["yfinance", "newsapi", "sec_edgar", "alpha_vantage", "rss", "stocktwits"] = (
        Field(description="Data provider")
    )

    @field_validator("provider", mode="before")
    @classmethod
    def _normalize_provider(cls, v: object) -> object:
        return _normalize_literal(v)


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
    sec_notes: str | None = None
    news_summary: str | None = None

    @field_validator("ticker", mode="before")
    @classmethod
    def _normalize_ticker(cls, v: object) -> object:
        if isinstance(v, str):
            return _normalize_ticker(v)
        return v

    @field_validator("signal", "confidence", mode="before")
    @classmethod
    def _normalize_literals(cls, v: object) -> object:
        return _normalize_literal(v)


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

    @field_validator("intent", mode="before")
    @classmethod
    def _normalize_intent(cls, v: object) -> object:
        return _normalize_literal(v)

    @field_validator("tickers", mode="before")
    @classmethod
    def _normalize_tickers(cls, v: object) -> object:
        if isinstance(v, list):
            return [_normalize_ticker(t) if isinstance(t, str) else t for t in v]
        return v

    @model_validator(mode="after")
    def _check_intent_tickers(self) -> RouterOutput:
        """Ensure ticker-dependent intents have at least one ticker."""
        needs_ticker = {"single_ticker", "add_position", "remove_position"}
        if self.intent in needs_ticker and not self.tickers:
            msg = f"intent '{self.intent}' requires at least one ticker"
            raise ValueError(msg)
        return self
