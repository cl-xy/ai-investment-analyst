"""Pydantic models for auto sector-peer comparison (Feature 2)."""

from typing import Literal

from pydantic import BaseModel, Field


class PeerSnapshot(BaseModel):
    """Lightweight peer context — never the product of a full debate."""

    ticker: str
    source: Literal["cached_analysis", "fundamentals_only"]
    signal: str | None = None
    confidence: str | None = None
    current_price: float | None = None
    pe_ratio: float | None = None
    revenue_growth_yoy: float | None = None
    profit_margin: float | None = None


class PeerComparisonResult(BaseModel):
    primary: str
    sector: str
    peers: list[PeerSnapshot] = Field(default_factory=list)
