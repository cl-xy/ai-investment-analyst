"""
Adversarial debate node. Replaces single-shot analyze_ticker with a 3-agent debate.

Protocol: Bull (argues long) -> Bear (rebuts + argues short) -> Moderator (verdict)
Each agent uses OpenRouter JSON mode + Pydantic validation with 1 retry on failure.
Falls back to single-shot analysis if debate fails or rate budget is exhausted.
"""

import asyncio
import json
import logging
import os
import time
from functools import cache
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ..circuit_breaker import CircuitBreakerOpen, llm_breaker
from ..debate_schemas import (
    BearCaseOutput,
    BullCaseOutput,
    DebateRecord,
    ModeratorOutput,
)
from ..json_utils import extract_json
from ..prompts.debate_prompts import (
    BEAR_HUMAN,
    BEAR_SYSTEM,
    BULL_HUMAN,
    BULL_SYSTEM,
    MODERATOR_HUMAN,
    MODERATOR_SYSTEM,
)
from ..state import InvestmentAnalystState, TickerAnalysis

log = logging.getLogger(__name__)

# Minimum delay between sequential LLM calls to stay under 30 req/min
_MIN_CALL_INTERVAL = 2.5  # seconds


def _is_retryable_error(exc: BaseException) -> bool:
    """Return True for transient errors that should be retried."""
    import re

    exc_str = str(exc).lower()
    if any(code in exc_str for code in ("401", "400", "unauthorized", "bad request")):
        return False
    if re.search(r"\b(429|500|502|503)\b", exc_str):
        return True
    if "rate limit" in exc_str:
        return True
    if any(term in exc_str for term in ("timeout", "connection", "temporary", "unavailable")):
        return True
    return False


@cache
def _get_llm() -> ChatOpenAI:
    from ...config import settings

    api_key = settings.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable is not set")
    return ChatOpenAI(
        model=settings.llm_model,
        temperature=0.3,  # slightly higher than 0 for diverse debate perspectives
        max_tokens=8192,  # type: ignore[call-arg]
        base_url=settings.llm_base_url,
        api_key=api_key,  # type: ignore[arg-type]
        model_kwargs={"response_format": {"type": "json_object"}},
        request_timeout=120,  # type: ignore[call-arg]
    )


@retry(
    retry=retry_if_exception(_is_retryable_error),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    stop=stop_after_attempt(2),
    reraise=True,
)
async def _invoke_with_retry(messages: list) -> BaseMessage:
    """Invoke LLM with retry and circuit breaker (which handles rate limiting)."""
    return await llm_breaker.call(_get_llm().ainvoke, messages)  # type: ignore[return-value]


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
    price_data: dict = state.get("raw_prices", {}).get(ticker, {})
    news = state.get("raw_news", {}).get(ticker, [])
    sec_text = state.get("raw_filings", {}).get(ticker, "") or "Not available."

    return {
        "ticker": ticker,
        "price_data": json.dumps(price_data.get("quote", {}), indent=2),
        "price_source_id": _make_source_id("yfinance", ticker),
        "fundamentals": json.dumps(price_data.get("fundamentals", {}), indent=2),
        "fundamentals_source_id": _make_source_id("yfinance", ticker),
        "indicators": json.dumps(price_data.get("indicators", {}), indent=2),
        "indicators_source_id": _make_source_id("yfinance", ticker),
        "article_count": len(news),
        "news_text": _format_news(news),
        "news_source_id": _make_source_id("newsapi", ticker),
        "sec_notes": sec_text[:1500],
        "sec_source_id": _make_source_id("sec_edgar", ticker),
        "raw_price_data": price_data,
    }


async def _run_bull_agent(ctx: dict[str, Any]) -> BullCaseOutput:
    """Run the bull analyst agent."""
    prompt = BULL_HUMAN.format(**{k: v for k, v in ctx.items() if k != "raw_price_data"})
    messages = [SystemMessage(content=BULL_SYSTEM), HumanMessage(content=prompt)]

    response = await _invoke_with_retry(messages)

    try:
        return BullCaseOutput.model_validate_json(response.content)
    except (ValidationError, ValueError):
        # Retry with error feedback
        retry_msg = HumanMessage(
            content="Your JSON was invalid. Return valid JSON matching the schema exactly."
        )
        retry_response = await _invoke_with_retry(messages + [retry_msg])
        try:
            return BullCaseOutput.model_validate_json(retry_response.content)
        except (ValidationError, ValueError):
            # Fallback: extract what we can
            parsed = extract_json(response.content)
            if isinstance(parsed, dict):
                return BullCaseOutput(
                    ticker=ctx["ticker"],
                    thesis=parsed.get("thesis", "Bull case generation failed"),
                    key_arguments=parsed.get("key_arguments", []),
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
        **{k: v for k, v in ctx.items() if k != "raw_price_data"},
    )
    messages = [SystemMessage(content=BEAR_SYSTEM), HumanMessage(content=prompt)]

    response = await _invoke_with_retry(messages)

    try:
        return BearCaseOutput.model_validate_json(response.content)
    except (ValidationError, ValueError):
        retry_msg = HumanMessage(
            content="Your JSON was invalid. Return valid JSON matching the schema exactly."
        )
        retry_response = await _invoke_with_retry(messages + [retry_msg])
        try:
            return BearCaseOutput.model_validate_json(retry_response.content)
        except (ValidationError, ValueError):
            parsed = extract_json(response.content)
            if isinstance(parsed, dict):
                return BearCaseOutput(
                    ticker=ctx["ticker"],
                    thesis=parsed.get("thesis", "Bear case generation failed"),
                    key_arguments=parsed.get("key_arguments", []),
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
        **{k: v for k, v in ctx.items() if k != "raw_price_data"},
    )
    messages = [SystemMessage(content=MODERATOR_SYSTEM), HumanMessage(content=prompt)]

    response = await _invoke_with_retry(messages)

    try:
        return ModeratorOutput.model_validate_json(response.content)
    except (ValidationError, ValueError):
        retry_msg = HumanMessage(
            content="Your JSON was invalid. Return valid JSON matching the schema exactly."
        )
        retry_response = await _invoke_with_retry(messages + [retry_msg])
        try:
            return ModeratorOutput.model_validate_json(retry_response.content)
        except (ValidationError, ValueError):
            parsed = extract_json(response.content)
            if isinstance(parsed, dict):
                return ModeratorOutput(
                    ticker=ctx["ticker"],
                    signal=parsed.get("signal", "insufficient_data"),
                    confidence=parsed.get("confidence", "low"),
                    sentiment_score=float(parsed.get("sentiment_score", 0.0)),
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
    ctx = _build_data_context(ticker, state)
    price_data = ctx["raw_price_data"]

    log.info("debate_starting ticker=%s", ticker)

    # Run bull agent
    bull_start = time.monotonic()
    try:
        bull = await _run_bull_agent(ctx)
        bull_duration = int((time.monotonic() - bull_start) * 1000)
        log.info(
            "bull_complete ticker=%s confidence=%s ms=%d", ticker, bull.confidence, bull_duration
        )
    except (CircuitBreakerOpen, Exception) as e:
        log.warning("bull_failed ticker=%s error=%s", ticker, e)
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
        log.info(
            "bear_complete ticker=%s confidence=%s ms=%d", ticker, bear.confidence, bear_duration
        )
    except (CircuitBreakerOpen, Exception) as e:
        log.warning("bear_failed ticker=%s error=%s", ticker, e)
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
        log.info(
            "moderator_complete ticker=%s signal=%s confidence=%s ms=%d",
            ticker,
            moderator.signal,
            moderator.confidence,
            mod_duration,
        )
    except (CircuitBreakerOpen, Exception) as e:
        log.warning("moderator_failed ticker=%s error=%s", ticker, e)
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
            "sec_notes": "",
        }
        existing = dict(state.get("ticker_analyses", {}))
        existing[ticker] = analysis
        return {"ticker_analyses": existing, "current_ticker": ticker}

    # Build the debate record for persistence
    debate_record = DebateRecord(
        ticker=ticker,
        bull=bull,
        bear=bear,
        moderator=moderator,
    )

    # Convert moderator output to the standard TickerAnalysis format
    analysis: dict[str, Any] = {
        "ticker": moderator.ticker,
        "signal": moderator.signal,
        "confidence": moderator.confidence,
        "sentiment_score": moderator.sentiment_score,
        "thesis": moderator.thesis,
        "bull_case": moderator.bull_case,
        "bear_case": moderator.bear_case,
        "news_summary": moderator.news_summary or moderator.thesis,
        "risk_flags": moderator.risk_flags,
        "citations": [c.model_dump() for c in moderator.citations],
        "data_gaps": moderator.data_gaps,
        "price_data": price_data.get("quote", {}),
        "fundamentals": price_data.get("fundamentals", {}),
        "sec_notes": moderator.sec_notes,
        # Debate-specific fields for persistence
        "_debate": debate_record.model_dump(),
        "_verdict_rationale": moderator.verdict_rationale,
        "_key_disagreements": moderator.key_disagreements,
    }

    existing = dict(state.get("ticker_analyses", {}))
    existing[ticker] = analysis
    return {"ticker_analyses": existing, "current_ticker": ticker}
