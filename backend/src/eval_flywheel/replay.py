"""
Frozen-input debate-core replay evaluator (Task 4).

Reruns the actual bull -> bear -> moderator debate functions from
src/agent/nodes/debate.py against a promoted evaluation case's captured,
point-in-time tool payloads. Zero live tool/network calls: all data comes
from evidence_artifacts.full_payload via capture.py's load_case_tool_payloads.

Scope, explicitly: this replays the DEBATE REASONING CORE only —
_build_data_context + _run_bull_agent + _run_bear_agent + _run_moderator —
not the full LangGraph pipeline. It does NOT exercise:
  - fetch_data_node's gap-detection / cache-vs-live branching logic
  - graph-level routing (build_graph / _route_after_router etc.)
  - the live MCP tool servers at all
A full graph-level replay would require constructing fake LangChain-Tool-
compatible objects to substitute for the live MCP client tools threaded
through build_graph(mcp_tools) — out of scope for this iteration. Any
dashboard/report copy describing this feature must say "debate reasoning
replay", not "full pipeline replay".

No-hindsight-leakage guarantee: this module never reads predictions.outcome,
predictions.realized_return, or any other resolution field. It only reads
from evaluation_case_artifacts / evidence_artifacts, which are populated at
analysis time, before any outcome exists. Scoring against the outcome
happens later, in scoring.py, strictly on the OUTPUT of replay — never as
replay input.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, cast

from src.agent.debate_schemas import BearCaseOutput, BullCaseOutput, ModeratorOutput
from src.agent.nodes.debate import (
    _build_data_context,
    _run_bear_agent,
    _run_bull_agent,
    _run_moderator,
)
from src.agent.state import InvestmentAnalystState
from src.eval_flywheel.capture import load_case_tool_payloads
from src.evidence.registry import RunEvidence

ReplayStatus = Literal["completed", "schema_failed", "timeout", "error", "not_replayable"]

# Fields that must NEVER appear in a reconstructed state slice, because they
# encode resolution information the original debate did not have access to.
# Asserted against defensively in _reconstruct_state, not just documented.
_FORBIDDEN_OUTCOME_KEYS = frozenset(
    {"outcome", "realized_return", "excess_return", "outcome_price", "resolved_at"}
)

# Maps evidence_artifacts (provider, tool) pairs back to the raw_* state keys
# _build_data_context expects. Mirrors fetch_data_node's fixed 7-tool set.
_TOOL_TO_STATE_SLOT: dict[str, str] = {
    "newsapi:get_ticker_news": "raw_news",
    "yfinance:get_quote": "raw_prices.quote",
    "yfinance:get_fundamentals": "raw_prices.fundamentals",
    "yfinance:get_technical_indicators": "raw_prices.indicators",
    "sec_edgar:get_latest_filing_summary": "raw_filings",
    "yfinance:get_earnings_calendar": "raw_earnings",
    "stocktwits:get_ticker_sentiment": "raw_sentiment",
}


@dataclass(frozen=True, slots=True)
class ReplayResult:
    case_id: str
    status: ReplayStatus
    output: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int = 0
    tokens_used: int = 0


def _reconstruct_state(ticker: str, grouped_payloads: dict[str, list[dict]]) -> dict[str, Any]:
    """Build the minimal state dict _build_data_context needs, from grouped
    (provider:tool -> [{ticker, payload}]) tool payloads.

    Raises AssertionError if any forbidden outcome-bearing key is present —
    this should be structurally impossible given the source tables, but is
    asserted here as a hard guarantee, not just a convention.
    """
    raw_news: list = []
    raw_prices: dict[str, Any] = {"quote": {}, "fundamentals": {}, "indicators": {}}
    raw_filings: str = ""
    raw_earnings: dict[str, Any] = {}
    raw_sentiment: dict[str, Any] = {}

    run_evidence = RunEvidence(run_id=f"replay-{ticker}")

    for key, entries in grouped_payloads.items():
        slot = _TOOL_TO_STATE_SLOT.get(key)
        if slot is None:
            continue
        provider, tool = key.split(":", 1)
        matching = [e for e in entries if e["ticker"] == ticker]
        if not matching:
            continue
        payload = matching[0]["payload"]

        assert not (isinstance(payload, dict) and _FORBIDDEN_OUTCOME_KEYS & payload.keys()), (
            f"outcome-bearing key found in replay input for {key} — hindsight leakage"
        )

        if slot == "raw_news":
            raw_news = payload if isinstance(payload, list) else []
        elif slot == "raw_prices.quote":
            raw_prices["quote"] = payload if isinstance(payload, dict) else {}
        elif slot == "raw_prices.fundamentals":
            raw_prices["fundamentals"] = payload if isinstance(payload, dict) else {}
        elif slot == "raw_prices.indicators":
            raw_prices["indicators"] = payload if isinstance(payload, dict) else {}
        elif slot == "raw_filings":
            raw_filings = payload if isinstance(payload, str) else ""
        elif slot == "raw_earnings":
            raw_earnings = payload if isinstance(payload, dict) else {}
        elif slot == "raw_sentiment":
            raw_sentiment = payload if isinstance(payload, dict) else {}

        # Re-register into a fresh RunEvidence so _build_data_context's
        # artifact-ID lookups resolve exactly as they did originally.
        run_evidence.register(provider, tool, ticker, payload)

    return {
        "raw_news": {ticker: raw_news},
        "raw_prices": {ticker: raw_prices},
        "raw_filings": {ticker: raw_filings},
        "raw_earnings": {ticker: raw_earnings},
        "raw_sentiment": {ticker: raw_sentiment},
        "run_evidence": run_evidence,
        "correlation_id": None,
    }


async def replay_case(case_id: str, ticker: str, *, timeout_seconds: int = 180) -> ReplayResult:
    """Replay one promoted case's debate core against its frozen inputs.

    Returns a ReplayResult even on failure — callers persist every attempt,
    matching the tolerant-degradation contract debate_ticker_node itself
    uses in production.
    """
    import asyncio

    grouped = await load_case_tool_payloads(case_id)
    if grouped is None:
        return ReplayResult(
            case_id=case_id,
            status="not_replayable",
            error="capture_status is not 'complete' or no artifacts found",
        )

    try:
        state = _reconstruct_state(ticker, grouped)
    except AssertionError as exc:
        return ReplayResult(case_id=case_id, status="error", error=str(exc))

    start = time.monotonic()
    try:
        ctx = await asyncio.wait_for(_run_replay_debate(ticker, state), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return ReplayResult(
            case_id=case_id,
            status="timeout",
            latency_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as exc:
        return ReplayResult(
            case_id=case_id,
            status="error",
            error=str(exc)[:500],
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    latency_ms = int((time.monotonic() - start) * 1000)
    return ReplayResult(
        case_id=case_id,
        status="completed",
        output=ctx,
        latency_ms=latency_ms,
    )


async def _run_replay_debate(ticker: str, state: dict[str, Any]) -> dict[str, Any]:
    """Run bull -> bear -> moderator directly (bypasses fetch_data_node and
    build_graph entirely). Returns a dict shaped like the debate's normal
    analysis_result, for reuse by scoring.py.

    `_run_evidence` is carried in the output (not just the input state) so
    scoring.py can call validate_citations() against the SAME RunEvidence
    used during this replay — citations reference artifact IDs registered
    here, not the original run's ledger, since replay rebuilds evidence
    from scratch in _reconstruct_state.
    """
    # `state` is intentionally a partial slice of InvestmentAnalystState
    # (only the raw_* fields _build_data_context reads, plus run_evidence),
    # not a full valid graph state — messages/intent/tickers_to_analyze etc.
    # are absent since replay never touches the graph. The cast documents
    # this deliberate narrowing rather than widening _build_data_context's
    # signature to accept a looser type.
    ctx = _build_data_context(ticker, cast(InvestmentAnalystState, state))

    bull: BullCaseOutput = await _run_bull_agent(ctx)
    bear: BearCaseOutput = await _run_bear_agent(ctx, bull)
    moderator: ModeratorOutput = await _run_moderator(ctx, bull, bear)

    return {
        "ticker": ticker,
        "signal": moderator.signal,
        "confidence": moderator.confidence,
        "sentiment_score": moderator.sentiment_score,
        "thesis": moderator.thesis,
        "bull_case": moderator.bull_case,
        "bear_case": moderator.bear_case,
        "risk_flags": moderator.risk_flags,
        "citations": [c.model_dump() for c in moderator.citations],
        "data_gaps": moderator.data_gaps,
        "_bull_evidence_count": len(bull.evidence),
        "_bear_evidence_count": len(bear.evidence),
        "_replayed_at": datetime.now(timezone.utc).isoformat(),
        "_run_evidence": state.get("run_evidence"),
    }


@dataclass
class BatchReplayResult:
    results: list[ReplayResult] = field(default_factory=list)

    @property
    def completed_count(self) -> int:
        return sum(1 for r in self.results if r.status == "completed")


async def replay_cases_batch(cases: list[tuple[str, str]]) -> BatchReplayResult:
    """Replay a batch of (case_id, ticker) pairs in deterministic order.

    Sequential, not parallel: mirrors debate_ticker_node's own sequential
    bull->bear->moderator rate-limited pattern and keeps this bounded within
    the same free-tier LLM budget constraints as production.
    """
    results: list[ReplayResult] = []
    for case_id, ticker in cases:
        result = await replay_case(case_id, ticker)
        results.append(result)
    return BatchReplayResult(results=results)
