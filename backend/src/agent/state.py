from __future__ import annotations

from typing import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class TickerAnalysis(TypedDict):
    ticker: str
    signal: Literal["buy", "hold", "sell", "insufficient_data"]
    confidence: Literal["high", "medium", "low"]
    sentiment_score: float
    news_summary: str
    risk_flags: list[str]
    price_data: dict
    fundamentals: dict
    sec_notes: str


class PortfolioPosition(TypedDict):
    ticker: str
    shares: float
    cost_basis: float
    sector: str
    added_date: str


class InvestmentAnalystState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

    intent: Literal[
        "full_report",
        "single_ticker",
        "add_position",
        "remove_position",
        "list_portfolio",
        "conversational",
    ]

    tickers_to_analyze: list[str]
    portfolio: list[PortfolioPosition]

    ticker_analyses: dict[str, TickerAnalysis]

    raw_news: dict[str, list[dict]]
    raw_prices: dict[str, dict]
    raw_filings: dict[str, str]

    # Graceful degradation: tracks what data was unavailable
    data_gaps: list[str]

    report_markdown: str
    comparison: dict  # Optional comparative analysis (populated when 2+ tickers)
    current_ticker: str | None
    error: str | None
