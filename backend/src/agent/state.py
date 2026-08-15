from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired, TypedDict

if TYPE_CHECKING:
    from src.evidence.registry import RunEvidence


class TickerAnalysis(TypedDict):
    ticker: str
    signal: Literal["buy", "hold", "sell", "insufficient_data"]
    confidence: Literal["high", "medium", "low"]
    sentiment_score: float
    thesis: str
    bull_case: list[str]
    bear_case: list[str]
    news_summary: str
    risk_flags: list[str]
    citations: list[dict]
    data_gaps: list[str]
    price_data: dict
    fundamentals: dict
    earnings: dict
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

    # Populated by debate node (one ticker at a time, read-modify-write)
    ticker_analyses: NotRequired[dict[str, TickerAnalysis]]

    # Populated by fetch_data node
    raw_news: NotRequired[dict[str, list[dict]]]
    raw_prices: NotRequired[dict[str, dict]]
    raw_filings: NotRequired[dict[str, str]]
    raw_earnings: NotRequired[dict[str, dict]]
    raw_sentiment: NotRequired[dict[str, dict]]

    # Graceful degradation: tracks what data was unavailable (set by fetch_data)
    data_gaps: NotRequired[list[str]]

    # Evidence Integrity Ledger: immutable artifact registry for this run
    run_evidence: NotRequired["RunEvidence | None"]  # from src.evidence.registry

    report_markdown: NotRequired[str]
    comparison: NotRequired[dict | None]  # Populated when 2+ tickers analyzed
    peer_comparison: NotRequired[dict | None]  # Auto sector-peer context (single-ticker runs)
    current_ticker: NotRequired[str | None]
    error: NotRequired[str | None]

    # Correlation ID propagated from the request middleware for end-to-end tracing
    correlation_id: NotRequired[str | None]
