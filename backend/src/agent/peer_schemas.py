"""Pydantic models for auto sector-peer comparison (Feature 2)."""

from typing import Literal

from pydantic import BaseModel, Field


class PeerSnapshot(BaseModel):
    """Lightweight peer context — never the product of a full debate."""

    ticker: str
    source: Literal["cached_analysis", "fundamentals_only"]
    signal: Literal["buy", "hold", "sell", "insufficient_data"] | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    current_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    pe_ratio: float | None = Field(default=None, allow_inf_nan=False)
    revenue_growth_yoy: float | None = Field(default=None, allow_inf_nan=False)
    profit_margin: float | None = Field(default=None, allow_inf_nan=False)


class PeerComparisonResult(BaseModel):
    primary: str
    sector: str
    peers: list[PeerSnapshot] = Field(default_factory=list, max_length=10)
