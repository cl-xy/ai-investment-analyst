"""
Pydantic request/response schemas for the Investment Analyst API.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=1, description="List of ticker symbols to analyze")


class TickerAnalysis(BaseModel):
    ticker: str
    signal: Literal["buy", "hold", "sell", "insufficient_data"]
    confidence: Literal["high", "medium", "low"]
    sentiment_score: float
    news_summary: str
    risk_flags: list[str]
    price_data: dict
    fundamentals: dict
    sec_notes: str


class AnalyzeResponse(BaseModel):
    id: str
    tickers: list[str]
    report_markdown: str
    analyses: dict[str, TickerAnalysis]
    created_at: datetime


class AnalysisListItem(BaseModel):
    id: str
    tickers: list[str]
    created_at: datetime


class HealthResponse(BaseModel):
    status: str = "ok"


class TrendingStock(BaseModel):
    rank: int
    ticker: str
    name: str
    price: float | None
    change_pct: float | None
    volume: int | None


class ExploreResponse(BaseModel):
    stocks: list[TrendingStock]
    updated_at: datetime


class PricePoint(BaseModel):
    date: str
    close: float


class NewsItem(BaseModel):
    title: str
    url: str | None


class StockDetail(BaseModel):
    ticker: str
    industry: str | None
    description: str | None
    price_history: list[PricePoint]
    trending_reason: list[NewsItem]
