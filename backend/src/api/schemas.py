"""
Pydantic request/response schemas for the Investment Analyst API.
"""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Shared ticker validation regex. Alphanumeric + dots + hyphens, 1-10 chars.
# Must accept tickers like BRK-B, BRK.B (hyphens are valid in some systems).
VALID_TICKER_RE = re.compile(r"\A[A-Z0-9.\-]{1,10}\Z")


class AnalyzeRequest(BaseModel):
    tickers: list[str] = Field(
        ..., min_length=1, max_length=10, description="List of ticker symbols to analyze"
    )

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, v: list[str]) -> list[str]:
        """Normalize (strip/upper) and validate each ticker against the allowed pattern."""
        normalized = []
        seen: set[str] = set()
        for raw in v:
            t = raw.strip().upper()
            if not t:
                raise ValueError("Ticker must not be empty")
            if not VALID_TICKER_RE.match(t):
                raise ValueError(f"Invalid ticker symbol: {t!r}")
            if t not in seen:
                normalized.append(t)
                seen.add(t)
        if not normalized:
            raise ValueError("At least one valid ticker is required")
        return normalized


class TickerAnalysis(BaseModel):
    ticker: str
    signal: Literal["buy", "hold", "sell", "insufficient_data"] = "insufficient_data"
    confidence: Literal["high", "medium", "low"] = "low"
    sentiment_score: float = Field(0.0, ge=-1.0, le=1.0)
    news_summary: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    price_data: dict = Field(default_factory=dict)
    fundamentals: dict = Field(default_factory=dict)
    earnings: dict = Field(default_factory=dict)
    sec_notes: str = ""


class AnalyzeResponse(BaseModel):
    id: str
    tickers: list[str]
    report_markdown: str
    analyses: dict[str, TickerAnalysis]
    created_at: datetime
    comparison: dict | None = None
    peer_comparison: dict | None = None


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
    status: Literal["success", "skipped", "failed"]
    message: str
    tickers: list[str]
    analysis_id: str | None = None
    created_at: datetime
    duration_ms: int


class AlertEvaluationResponse(BaseModel):
    status: Literal["success", "skipped", "failed"]
    message: str
    tickers_evaluated: int = 0
    alerts_fired: int = 0
    llm_calls_used: int = 0
    heuristic_only_count: int = 0
    created_at: datetime
    duration_ms: int


# --- Reasoning-Aware Signal Alerts ---


class AlertItem(BaseModel):
    id: str
    ticker: str
    alert_type: str
    severity: Literal["info", "warning", "critical"]
    drift_score: float
    old_signal: str | None = None
    new_signal: str | None = None
    reasoning_diff: dict
    triggered_by: list[str]
    llm_judged: bool
    dispatched_telegram: bool
    created_at: datetime
    acknowledged_at: datetime | None = None


class AlertListResponse(BaseModel):
    alerts: list[AlertItem]
    total: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class SubscriptionRequest(BaseModel):
    ticker: str
    trigger_types: list[str] | None = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        t = v.strip().upper()
        if not VALID_TICKER_RE.match(t):
            raise ValueError(f"Invalid ticker symbol: {t!r}")
        return t


class SubscriptionItem(BaseModel):
    ticker: str
    source: str
    trigger_types: list[str]
    active: bool


class SubscriptionListResponse(BaseModel):
    subscriptions: list[SubscriptionItem]


# --- Compare ---


class CompareResponse(BaseModel):
    tickers: list[str]
    analyses: dict[str, TickerAnalysis]
    report_markdown: str
    comparison: dict | None = None


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
