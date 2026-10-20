"""Deterministic record of what each data source returned for a ticker.

The fetch layer knows exactly which calls succeeded, which came from cache and
why the rest failed. The moderator LLM does not, and used to write the
"data_gaps" banner from whatever it inferred from the prompt. This module is the
single place that turns fetch outcomes into (a) the banner lines shown to the
user and (b) an availability block the debate agents can read.
"""

from __future__ import annotations

import re
from typing import NamedTuple, TypedDict

OK = "ok"
CACHED = "cached"
STALE = "stale"
RATE_LIMITED = "rate_limited"
BLOCKED = "blocked"
TIMEOUT = "timeout"
EMPTY = "empty"
BUDGET = "budget_exhausted"
ERROR = "error"

# Statuses where the debate had real data to work with.
USABLE = frozenset({OK, CACHED, STALE})

_REASON = {
    RATE_LIMITED: "provider rate limited the request",
    BLOCKED: "provider blocked the request",
    TIMEOUT: "provider timed out",
    EMPTY: "no data returned",
    BUDGET: "daily request budget used up",
    ERROR: "fetch failed",
}


class SourceSpec(NamedTuple):
    label: str
    # Words a free-text caveat would use to refer to this source.
    keywords: tuple[str, ...]
    # Essential sources drive the "partial data" banner. Optional ones are
    # supplementary (a missing earnings date is normal, and retail sentiment
    # comes from a provider that currently challenges server traffic), so they
    # are recorded and shown to the debate agents but do not trigger the banner.
    essential: bool


SOURCES: dict[str, SourceSpec] = {
    "get_ticker_news": SourceSpec("News", ("news", "headline", "article"), True),
    "get_quote": SourceSpec(
        "Price quote", ("price", "quote", "market cap", "pe ratio", "p/e"), True
    ),
    "get_fundamentals": SourceSpec(
        "Fundamentals",
        ("fundamental", "revenue", "earnings per share", "eps", "margin", "balance sheet"),
        True,
    ),
    "get_latest_filing_summary": SourceSpec(
        "SEC filing", ("sec", "10-k", "10-q", "filing", "edgar"), True
    ),
    "get_technical_indicators": SourceSpec(
        "Technical indicators",
        ("technical", "indicator", "rsi", "macd", "moving average", "sma"),
        True,
    ),
    "get_earnings_calendar": SourceSpec("Earnings date", ("earnings date", "catalyst date"), False),
    "get_ticker_sentiment": SourceSpec(
        "Retail sentiment", ("sentiment", "stocktwits", "retail"), False
    ),
}


def tracked_source_mentioned(text: str) -> bool:
    """True if free text refers to a source the fetch layer already tracks."""
    low = text.lower()
    return any(
        re.search(rf"\b{re.escape(kw)}\b", low) for spec in SOURCES.values() for kw in spec.keywords
    )


class SourceStatus(TypedDict):
    status: str
    detail: str
    # Only set for STALE: how old the cached copy served after a failed refresh is.
    age_seconds: int | None


def classify_failure(message: str) -> str:
    """Map a tool/cache failure message to a status."""
    m = (message or "").lower()
    if "budget exhausted" in m:
        return BUDGET
    if "timeout" in m or "timed out" in m:
        return TIMEOUT
    if re.search(r"\b429\b", m) or "too many requests" in m or "rate limit" in m:
        return RATE_LIMITED
    if re.search(r"\b403\b", m) or "challenge" in m or "forbidden" in m or "blocked" in m:
        return BLOCKED
    if "empty data" in m or "no filings found" in m:
        return EMPTY
    return ERROR


def make_status(status: str, detail: str = "", age_seconds: int | None = None) -> SourceStatus:
    return {"status": status, "detail": detail[:200], "age_seconds": age_seconds}


def _age_text(seconds: int | None) -> str:
    if seconds is None:
        return "unknown age"
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def gap_lines(statuses: dict[str, SourceStatus]) -> list[str]:
    """Banner lines for essential sources that did not return fresh data."""
    lines: list[str] = []
    for tool, spec in SOURCES.items():
        entry = statuses.get(tool)
        if entry is None or not spec.essential:
            continue
        status = entry["status"]
        if status in (OK, CACHED):
            continue
        if status == STALE:
            lines.append(
                f"{spec.label}: showing cached data {_age_text(entry['age_seconds'])} old "
                "(provider unavailable)"
            )
        else:
            lines.append(f"{spec.label}: {_REASON.get(status, _REASON[ERROR])}")
    return lines


def failure_gap_texts(ticker: str, statuses: dict[str, SourceStatus]) -> list[str]:
    """Per-ticker lines for the run-level data_gaps list (all sources, with ticker)."""
    texts: list[str] = []
    for tool, spec in SOURCES.items():
        entry = statuses.get(tool)
        if entry is None or entry["status"] in USABLE:
            continue
        # Missing earnings are normal (many tickers have no confirmed date), so
        # an empty result there is not worth surfacing.
        if tool == "get_earnings_calendar" and entry["status"] != BUDGET:
            continue
        suffix = " (budget exhausted)" if entry["status"] == BUDGET else ""
        texts.append(f"{spec.label} unavailable for {ticker}{suffix}")
    return texts


def format_for_prompt(statuses: dict[str, SourceStatus]) -> str:
    """Availability block for the moderator, covering every source."""
    if not statuses:
        return "No fetch record available."
    lines: list[str] = []
    for tool, spec in SOURCES.items():
        entry = statuses.get(tool)
        if entry is None:
            continue
        status = entry["status"]
        if status in (OK, CACHED):
            lines.append(f"- {spec.label}: available")
        elif status == STALE:
            lines.append(
                f"- {spec.label}: available but stale ({_age_text(entry['age_seconds'])} old)"
            )
        else:
            lines.append(f"- {spec.label}: UNAVAILABLE ({_REASON.get(status, _REASON[ERROR])})")
    return "\n".join(lines)
