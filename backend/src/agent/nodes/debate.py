"""
Adversarial debate node. Replaces single-shot analyze_ticker with a 3-agent debate.

Protocol: Bull (argues long) -> Bear (rebuts + argues short) -> Moderator (verdict)
Each agent uses OpenRouter JSON mode + Pydantic validation with 1 retry on failure.
Falls back to single-shot analysis if debate fails or rate budget is exhausted.
"""

import asyncio
import json
import time
from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from src.logging_config import get_logger
from src.numeric import safe_float as _safe_float

from ..circuit_breaker import CircuitBreakerOpen
from ..debate_schemas import (
    BearCaseOutput,
    BullCaseOutput,
    DebateRecord,
    ModeratorOutput,
)
from ..json_utils import extract_json as _extract_json_raw
from ..llm_fallback import invoke_with_fallback
from ..prompts.debate_prompts import (
    BEAR_HUMAN,
    BEAR_SYSTEM,
    BULL_HUMAN,
    BULL_SYSTEM,
    MODERATOR_HUMAN,
    MODERATOR_SYSTEM,
)
from ..state import InvestmentAnalystState, TickerAnalysis

log = get_logger(__name__)

# Minimum delay between sequential LLM calls to reduce burst contention
# on free-tier provider workers (Nvidia ResourceExhausted threshold)
_MIN_CALL_INTERVAL = 4.0  # seconds


def _coerce_str_list(items: list) -> list[str]:
    """Coerce list items to strings. Handles LLM returning objects instead of plain strings."""
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.append(item.get("claim") or item.get("text") or str(item))
        else:
            result.append(str(item))
    return result


def _dedup_text(text: str) -> str:
    """Remove repeated sentences/phrases from LLM output.

    Free-tier models (nemotron-120b) occasionally enter generation loops,
    producing the same sentence 5-20 times. This strips consecutive and
    non-consecutive duplicates while preserving order of first occurrence.
    """
    if not text or len(text) < 100:
        return text
    # Split on sentence boundaries (period, newline)
    import re as _re

    sentences = _re.split(r"(?<=[.!?\n])\s+", text)
    if len(sentences) < 4:
        return text
    seen: set[str] = set()
    deduped: list[str] = []
    for s in sentences:
        normalized = s.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(s)
    result = " ".join(deduped)
    # If we removed more than 30% of sentences, the model was looping
    if len(deduped) < len(sentences) * 0.7:
        log.warning(
            "dedup_stripped_repetition", original_sentences=len(sentences), kept=len(deduped)
        )
    return result


def _normalize_content(content) -> str:
    """Normalize LangChain message content to a plain string.

    LangChain providers can return content as either a str or a list of
    content blocks (e.g. [{"type": "text", "text": "..."}]). This ensures
    downstream JSON parsing always receives a string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def _safe_extract_json(text: str) -> dict | None:
    """Extract JSON dict from LLM text, returning None on failure or non-dict."""
    try:
        parsed = _extract_json_raw(text)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    if isinstance(parsed, dict):
        return parsed
    # extract_json can return a list; take first dict element if available
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                return item
    return None


async def _invoke_with_retry(messages: list) -> object:
    """Invoke LLM with retry + model fallback for debate steps.

    Uses higher temperature for diverse debate perspectives.
    """
    return await invoke_with_fallback(
        messages, temperature=0.5, max_tokens=8192, request_timeout=120
    )


def _format_sentiment(sentiment: dict) -> str:
    if not sentiment or not sentiment.get("message_count"):
        return "No StockTwits sentiment data available."
    lines = [
        f"Messages analyzed: {sentiment.get('message_count', 0)}",
        f"Bullish: {sentiment.get('bullish_count', 0)}, Bearish: {sentiment.get('bearish_count', 0)}, "
        f"Unlabeled: {sentiment.get('unlabeled_count', 0)}",
    ]
    ratio = sentiment.get("bullish_ratio")
    if ratio is not None:
        lines.append(f"Bullish ratio (of labeled messages): {ratio}")
    samples = sentiment.get("sample_messages") or []
    if samples:
        lines.append("Sample messages:")
        for s in samples[:3]:
            lines.append(f"  - {s}")
    return "\n".join(lines)


def _format_news(articles: list[dict]) -> str:
    if not articles:
        return "No recent news available."
    lines = []
    for i, a in enumerate(articles[:10], 1):
        lines.append(f"{i}. [{a.get('source', 'Unknown')}] {a.get('title', '')}")
        if a.get("snippet"):
            lines.append(f"   {a['snippet'][:200]}")
        lines.append(f"   Published: {a.get('published_at', 'unknown')}")
    return "\n".join(lines)


def _make_source_id(provider: str, ticker: str) -> str:
    return f"{provider}:{ticker}:{int(time.time())}"


def _build_data_context(ticker: str, state: InvestmentAnalystState) -> dict[str, Any]:
    """Extract and format data context from state for prompt injection."""
    price_data: dict = state.get("raw_prices", {}).get(ticker) or {}
    news = state.get("raw_news", {}).get(ticker) or []
    sec_text = state.get("raw_filings", {}).get(ticker) or "Not available."
    earnings = state.get("raw_earnings", {}).get(ticker) or {}
    sentiment = state.get("raw_sentiment", {}).get(ticker) or {}

    return {
        "ticker": ticker,
        "current_date": date.today().isoformat(),
        "price_data": json.dumps(price_data.get("quote", {}), indent=2),
        "price_source_id": _make_source_id("yfinance", ticker),
        "fundamentals": json.dumps(price_data.get("fundamentals", {}), indent=2),
        "fundamentals_source_id": _make_source_id("yfinance", ticker),
        "indicators": json.dumps(price_data.get("indicators", {}), indent=2),
        "indicators_source_id": _make_source_id("yfinance", ticker),
        "earnings": json.dumps(earnings, indent=2)
        if earnings
        else "No confirmed upcoming earnings date.",
        "earnings_source_id": _make_source_id("yfinance", ticker),
        "article_count": len(news),
        "news_text": _format_news(news),
        "news_source_id": _make_source_id("newsapi", ticker),
        "sentiment_text": _format_sentiment(sentiment),
        "sentiment_source_id": _make_source_id("stocktwits", ticker),
        "sec_notes": sec_text[:1500],
        "sec_source_id": _make_source_id("sec_edgar", ticker),
        "raw_price_data": price_data,
        "raw_earnings": earnings,
        "raw_sentiment": sentiment,
    }


async def _run_bull_agent(ctx: dict[str, Any]) -> BullCaseOutput:
    """Run the bull analyst agent."""
    prompt = BULL_HUMAN.format(
        **{
            k: v
            for k, v in ctx.items()
            if k not in ("raw_price_data", "raw_earnings", "raw_sentiment")
        }
    )
    messages = [SystemMessage(content=BULL_SYSTEM), HumanMessage(content=prompt)]

    response = await _invoke_with_retry(messages)
    content = _normalize_content(response.content)

    try:
        return BullCaseOutput.model_validate_json(content)
    except (ValidationError, ValueError, TypeError):
        # Retry with error feedback
        retry_msg = HumanMessage(
            content="Your JSON was invalid. Return valid JSON matching the schema exactly."
        )
        retry_response = await _invoke_with_retry(messages + [retry_msg])
        retry_content = _normalize_content(retry_response.content)
        try:
            return BullCaseOutput.model_validate_json(retry_content)
        except (ValidationError, ValueError, TypeError):
            # Fallback: try retry response first, then original
            parsed = _safe_extract_json(retry_content) or _safe_extract_json(content)
            if parsed:
                return BullCaseOutput(
                    ticker=ctx["ticker"],
                    thesis=parsed.get("thesis", "Bull case generation failed"),
                    key_arguments=_coerce_str_list(parsed.get("key_arguments", [])),
                    confidence=parsed.get("confidence", "low"),
                )
            return BullCaseOutput(
                ticker=ctx["ticker"],
                thesis="Bull case generation failed",
                confidence="low",
            )


async def _run_bear_agent(ctx: dict[str, Any], bull: BullCaseOutput) -> BearCaseOutput:
    """Run the bear analyst agent with access to the bull case."""
    prompt = BEAR_HUMAN.format(
        bull_thesis=bull.thesis,
        bull_arguments=json.dumps(bull.key_arguments, indent=2),
        **{
            k: v
            for k, v in ctx.items()
            if k not in ("raw_price_data", "raw_earnings", "raw_sentiment")
        },
    )
    messages = [SystemMessage(content=BEAR_SYSTEM), HumanMessage(content=prompt)]

    response = await _invoke_with_retry(messages)
    content = _normalize_content(response.content)

    try:
        return BearCaseOutput.model_validate_json(content)
    except (ValidationError, ValueError, TypeError):
        retry_msg = HumanMessage(
            content="Your JSON was invalid. Return valid JSON matching the schema exactly."
        )
        retry_response = await _invoke_with_retry(messages + [retry_msg])
        retry_content = _normalize_content(retry_response.content)
        try:
            return BearCaseOutput.model_validate_json(retry_content)
        except (ValidationError, ValueError, TypeError):
            parsed = _safe_extract_json(retry_content) or _safe_extract_json(content)
            if parsed:
                return BearCaseOutput(
                    ticker=ctx["ticker"],
                    thesis=parsed.get("thesis", "Bear case generation failed"),
                    key_arguments=_coerce_str_list(parsed.get("key_arguments", [])),
                    confidence=parsed.get("confidence", "low"),
                )
            return BearCaseOutput(
                ticker=ctx["ticker"],
                thesis="Bear case generation failed",
                confidence="low",
            )


async def _run_moderator(
    ctx: dict[str, Any], bull: BullCaseOutput, bear: BearCaseOutput
) -> ModeratorOutput:
    """Run the moderator/CIO agent to issue final verdict."""
    prompt = MODERATOR_HUMAN.format(
        bull_confidence=bull.confidence,
        bull_thesis=bull.thesis,
        bull_arguments=json.dumps(bull.key_arguments, indent=2),
        bull_catalysts=json.dumps(bull.catalysts, indent=2),
        bull_evidence=json.dumps([e.model_dump() for e in bull.evidence], indent=2),
        bull_risks=json.dumps(bull.acknowledged_risks, indent=2),
        bear_confidence=bear.confidence,
        bear_thesis=bear.thesis,
        bear_arguments=json.dumps(bear.key_arguments, indent=2),
        bear_rebuttals=json.dumps([r.model_dump() for r in bear.rebuttals], indent=2),
        bear_risk_flags=json.dumps(bear.risk_flags, indent=2),
        bear_evidence=json.dumps([e.model_dump() for e in bear.evidence], indent=2),
        bear_concessions=json.dumps(bear.conceded_strengths, indent=2),
        **{
            k: v
            for k, v in ctx.items()
            if k not in ("raw_price_data", "raw_earnings", "raw_sentiment")
        },
    )
    messages = [SystemMessage(content=MODERATOR_SYSTEM), HumanMessage(content=prompt)]

    response = await _invoke_with_retry(messages)
    content = _normalize_content(response.content)

    try:
        return ModeratorOutput.model_validate_json(content)
    except (ValidationError, ValueError, TypeError):
        retry_msg = HumanMessage(
            content="Your JSON was invalid. Return valid JSON matching the schema exactly."
        )
        retry_response = await _invoke_with_retry(messages + [retry_msg])
        retry_content = _normalize_content(retry_response.content)
        try:
            return ModeratorOutput.model_validate_json(retry_content)
        except (ValidationError, ValueError, TypeError):
            parsed = _safe_extract_json(retry_content) or _safe_extract_json(content)
            if parsed:
                return ModeratorOutput(
                    ticker=ctx["ticker"],
                    signal=parsed.get("signal", "insufficient_data"),
                    confidence=parsed.get("confidence", "low"),
                    sentiment_score=_safe_float(parsed.get("sentiment_score")),
                    thesis=parsed.get("thesis", "Moderator verdict generation failed"),
                    bull_case=parsed.get("bull_case", []),
                    bear_case=parsed.get("bear_case", []),
                    risk_flags=parsed.get("risk_flags", []),
                    data_gaps=parsed.get("data_gaps", ["Moderator output validation failed"]),
                )
            return ModeratorOutput(
                ticker=ctx["ticker"],
                signal="insufficient_data",
                confidence="low",
                sentiment_score=0.0,
                thesis="Moderator verdict generation failed",
                data_gaps=["Moderator output validation failed"],
            )


async def debate_ticker_node(state: InvestmentAnalystState) -> dict:
    """
    Run adversarial debate for the next unanalyzed ticker.

    Protocol: Bull -> Bear -> Moderator (sequential, rate-limited)
    Emits debate SSE events for real-time frontend rendering.
    Falls back to degraded output if any agent fails.
    """
    tickers_remaining = [
        t for t in state.get("tickers_to_analyze", []) if t not in state.get("ticker_analyses", {})
    ]
    if not tickers_remaining:
        return {}

    ticker = tickers_remaining[0]

    correlation_id = state.get("correlation_id")
    _log = (
        log.bind(correlation_id=correlation_id, node="debate", ticker=ticker)
        if correlation_id
        else log
    )

    try:
        ctx = _build_data_context(ticker, state)
    except Exception as e:
        _log.warning("context_build_failed", error=str(e))
        analysis: TickerAnalysis = {
            "ticker": ticker,
            "signal": "insufficient_data",
            "confidence": "low",
            "sentiment_score": 0.0,
            "thesis": f"Debate failed: data context error ({type(e).__name__})",
            "bull_case": [],
            "bear_case": [],
            "news_summary": "Analysis unavailable due to data preparation error",
            "risk_flags": ["Data context incomplete"],
            "citations": [],
            "data_gaps": [f"Context build failed: {str(e)[:100]}"],
            "price_data": {},
            "fundamentals": {},
            "earnings": {},
            "sec_notes": "",
        }
        existing = dict(state.get("ticker_analyses", {}))
        existing[ticker] = analysis
        return {"ticker_analyses": existing, "current_ticker": ticker}

    price_data = ctx["raw_price_data"]
    _log.info("debate_starting")

    # Run bull agent
    bull_start = time.monotonic()
    try:
        bull = await _run_bull_agent(ctx)
        bull_duration = int((time.monotonic() - bull_start) * 1000)
        _log.info("bull_complete", confidence=bull.confidence, duration_ms=bull_duration)
    except (CircuitBreakerOpen, Exception) as e:
        _log.warning("bull_failed", error=str(e))
        # Fallback: create minimal analysis without debate
        analysis: TickerAnalysis = {
            "ticker": ticker,
            "signal": "insufficient_data",
            "confidence": "low",
            "sentiment_score": 0.0,
            "thesis": f"Debate failed: bull agent error ({type(e).__name__})",
            "bull_case": [],
            "bear_case": [],
            "news_summary": "Analysis unavailable due to LLM service error",
            "risk_flags": ["Debate incomplete"],
            "citations": [],
            "data_gaps": [f"Bull agent failed: {str(e)[:100]}"],
            "price_data": price_data.get("quote", {}),
            "fundamentals": price_data.get("fundamentals", {}),
            "earnings": ctx.get("raw_earnings", {}),
            "sec_notes": "",
        }
        existing = dict(state.get("ticker_analyses", {}))
        existing[ticker] = analysis
        return {"ticker_analyses": existing, "current_ticker": ticker}

    # Rate limit pause between calls
    await asyncio.sleep(_MIN_CALL_INTERVAL)

    # Run bear agent
    bear_start = time.monotonic()
    try:
        bear = await _run_bear_agent(ctx, bull)
        bear_duration = int((time.monotonic() - bear_start) * 1000)
        _log.info("bear_complete", confidence=bear.confidence, duration_ms=bear_duration)
    except (CircuitBreakerOpen, Exception) as e:
        _log.warning("bear_failed", error=str(e))
        # Degrade: use bull-only analysis
        analysis = {
            "ticker": ticker,
            "signal": "hold",
            "confidence": "low",
            "sentiment_score": 0.3,
            "thesis": bull.thesis,
            "bull_case": bull.key_arguments,
            "bear_case": [],
            "news_summary": bull.thesis,
            "risk_flags": bull.acknowledged_risks,
            "citations": [e.model_dump() for e in bull.evidence],
            "data_gaps": [f"Bear agent failed: {str(e)[:100]}"],
            "price_data": price_data.get("quote", {}),
            "fundamentals": price_data.get("fundamentals", {}),
            "earnings": ctx.get("raw_earnings", {}),
            "sec_notes": "",
        }
        existing = dict(state.get("ticker_analyses", {}))
        existing[ticker] = analysis
        return {"ticker_analyses": existing, "current_ticker": ticker}

    # Rate limit pause
    await asyncio.sleep(_MIN_CALL_INTERVAL)

    # Run moderator
    mod_start = time.monotonic()
    try:
        moderator = await _run_moderator(ctx, bull, bear)
        mod_duration = int((time.monotonic() - mod_start) * 1000)
        _log.info(
            "moderator_complete",
            signal=moderator.signal,
            confidence=moderator.confidence,
            duration_ms=mod_duration,
        )
    except (CircuitBreakerOpen, Exception) as e:
        _log.warning("moderator_failed", error=str(e))
        # Degrade: synthesize from bull + bear without moderator
        analysis = {
            "ticker": ticker,
            "signal": "hold",
            "confidence": "low",
            "sentiment_score": 0.0,
            "thesis": f"Bull: {bull.thesis} | Bear: {bear.thesis}",
            "bull_case": bull.key_arguments,
            "bear_case": bear.key_arguments,
            "news_summary": bull.thesis,
            "risk_flags": bear.risk_flags,
            "citations": [e.model_dump() for e in bull.evidence]
            + [e.model_dump() for e in bear.evidence],
            "data_gaps": [f"Moderator failed: {str(e)[:100]}"],
            "price_data": price_data.get("quote", {}),
            "fundamentals": price_data.get("fundamentals", {}),
            "earnings": ctx.get("raw_earnings", {}),
            "sec_notes": "",
        }
        existing = dict(state.get("ticker_analyses", {}))
        existing[ticker] = analysis
        return {"ticker_analyses": existing, "current_ticker": ticker}

    # Build the debate record and final analysis safely
    try:
        debate_record = DebateRecord(
            ticker=ticker,
            bull=bull,
            bear=bear,
            moderator=moderator,
        )

        # Convert moderator output to the standard TickerAnalysis format
        # Apply dedup to free-form text fields to strip generation loops
        analysis_result: dict[str, Any] = {
            "ticker": ticker,
            "signal": moderator.signal,
            "confidence": moderator.confidence,
            "sentiment_score": moderator.sentiment_score,
            "thesis": _dedup_text(moderator.thesis),
            "bull_case": moderator.bull_case,
            "bear_case": moderator.bear_case,
            "news_summary": _dedup_text(moderator.news_summary or moderator.thesis),
            "risk_flags": moderator.risk_flags,
            "citations": [c.model_dump() for c in moderator.citations],
            "data_gaps": moderator.data_gaps,
            "price_data": price_data.get("quote", {}),
            "fundamentals": price_data.get("fundamentals", {}),
            "earnings": ctx.get("raw_earnings", {}),
            "sec_notes": moderator.sec_notes,
            # Debate-specific fields for persistence
            "_debate": debate_record.model_dump(),
            "_verdict_rationale": _dedup_text(moderator.verdict_rationale),
            "_key_disagreements": moderator.key_disagreements,
        }
    except Exception as e:
        _log.warning("result_assembly_failed", error=str(e))
        # All 3 agents succeeded but serialization failed; preserve core output
        analysis_result = {
            "ticker": ticker,
            "signal": moderator.signal,
            "confidence": moderator.confidence,
            "sentiment_score": moderator.sentiment_score,
            "thesis": moderator.thesis,
            "bull_case": getattr(moderator, "bull_case", []),
            "bear_case": getattr(moderator, "bear_case", []),
            "news_summary": getattr(moderator, "news_summary", "") or moderator.thesis,
            "risk_flags": getattr(moderator, "risk_flags", []),
            "citations": [],
            "data_gaps": [f"Result assembly failed: {str(e)[:100]}"],
            "price_data": price_data.get("quote", {}),
            "fundamentals": price_data.get("fundamentals", {}),
            "earnings": ctx.get("raw_earnings", {}),
            "sec_notes": "",
        }

    existing = dict(state.get("ticker_analyses", {}))
    existing[ticker] = analysis_result
    return {"ticker_analyses": existing, "current_ticker": ticker}
