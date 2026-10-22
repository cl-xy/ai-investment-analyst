from __future__ import annotations

from typing import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired, TypedDict

# Imported at runtime (not under TYPE_CHECKING) because LangGraph calls
# get_type_hints() on this TypedDict when building the graph, which evaluates
# the "RunEvidence | None" annotation. registry.py only depends on src.db, so
# there is no circular import.
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
    # Count of news articles the analysis was built on, captured at analysis
    # time so the drift scorer has a real baseline to diff fresh probe counts
    # against (see alerts/drift_scorer.py news_volume_spike). Optional: older
    # rows and degraded partials may omit it.
    article_count: NotRequired[int]
    # Debate turns that were answered by a backup model or with reasoning turned
    # off, as [{turn, model, reasoning_off}]. Empty/absent when the primary model
    # answered every turn normally, so the card only mentions it when it matters.
    fallback_turns: NotRequired[list[dict]]
    # Machine-readable completion status of the 3-agent debate. "complete" means
    # all three turns (bull, bear, moderator) ran and a moderator verdict was
    # synthesized. The "degraded_*" values name the first turn that failed; the
    # card still carries whatever market data and partial LLM output survived,
    # but it is NOT a finished debate and consumers that compare, aggregate,
    # alert on, or build peer baselines from analyses must be able to exclude or
    # down-weight it WITHOUT parsing free-text thesis/data_gaps. Absent on legacy
    # rows and on the normal success path only until it is set explicitly; treat
    # a missing value as "complete" for backward compatibility with stored rows
    # that predate this field. Runtime metadata (not persisted as its own DB
    # column yet) alongside _debate.
    debate_status: NotRequired[
        Literal["complete", "degraded_bull", "degraded_bear", "degraded_moderator"]
    ]


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

    # Per-ticker, per-tool outcome of the fetch (see agent/data_ledger.py).
    # The user-facing "partial data" banner is built from this, not from LLM prose.
    source_status: NotRequired[dict[str, dict[str, dict]]]

    # Evidence Integrity Ledger: immutable artifact registry for this run
    run_evidence: NotRequired[RunEvidence | None]

    report_markdown: NotRequired[str]
    # Whether the optional narrative report was generated, timed out, or failed.
    # A ticker analysis remains valid if this post-processing step is unavailable.
    report_status: NotRequired[Literal["generated", "timed_out", "failed"]]
    comparison: NotRequired[dict | None]  # Populated when 2+ tickers analyzed
    peer_comparison: NotRequired[dict | None]  # Auto sector-peer context (single-ticker runs)
    current_ticker: NotRequired[str | None]
    error: NotRequired[str | None]

    # Correlation ID propagated from the request middleware for end-to-end tracing
    correlation_id: NotRequired[str | None]
