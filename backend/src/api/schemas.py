"""
Pydantic request/response schemas for the Investment Analyst API.
"""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Shared ticker validation regex. Alphanumeric + dots, 1-10 chars.
VALID_TICKER_RE = re.compile(r"\A[A-Z0-9.]{1,10}\Z")


class AnalyzeRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=1, description="List of ticker symbols to analyze")


class TickerAnalysis(BaseModel):
    ticker: str
    signal: Literal["buy", "hold", "sell", "insufficient_data"] = "insufficient_data"
    confidence: Literal["high", "medium", "low"] = "low"
    sentiment_score: float = 0.0
    news_summary: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    price_data: dict = Field(default_factory=dict)
    fundamentals: dict = Field(default_factory=dict)
    sec_notes: str = ""


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


class ScheduledRefreshResponse(BaseModel):
    status: Literal["success", "skipped"]
    message: str
    tickers: list[str]
    analysis_id: str | None = None
    created_at: datetime
    duration_ms: int


# --- Compare ---


class CompareResponse(BaseModel):
    tickers: list[str]
    analyses: dict[str, TickerAnalysis]
    report_markdown: str


# --- Backtest ---


class SignalRecord(BaseModel):
    ticker: str
    signal: Literal["buy", "hold", "sell"]
    confidence: Literal["high", "medium", "low"]
    sentiment_score: float
    signal_date: str
    days_held: int
    analysis_id: str


class BacktestSummary(BaseModel):
    total: int
    buy_count: int = 0
    hold_count: int = 0
    sell_count: int = 0


class BacktestResponse(BaseModel):
    signals: list[SignalRecord]
    summary: BacktestSummary


# --- Eval ---


class EvalSummary(BaseModel):
    total_runs: int
    schema_validation_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    citation_coverage: float
    tool_success_rate: float
    cache_hit_rate: float
    last_run_at: str | None


class EvalDayRecord(BaseModel):
    date: str
    runs: int
    avg_latency_ms: int
    schema_validation_rate: float
    total_tokens: int


class EvalHistoryResponse(BaseModel):
    days: list[EvalDayRecord]
