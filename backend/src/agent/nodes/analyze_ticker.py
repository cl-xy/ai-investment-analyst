"""
Analyze ticker node — uses Groq JSON mode + Pydantic validation.

Replaces brittle extract_json() with structured output validation.
Single retry on validation failure.
"""

import json
import os
import time
from functools import cache

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from ..json_utils import extract_json
from ..prompts.analyst_prompt import ANALYST_HUMAN, ANALYST_SYSTEM
from ..state import InvestmentAnalystState, TickerAnalysis
from ..structured_output import AnalysisOutput


@cache
def _get_llm() -> ChatOpenAI:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set")
    return ChatOpenAI(
        model="openai/gpt-oss-120b",
        temperature=0,
        max_tokens=4096,
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


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


async def analyze_ticker_node(state: InvestmentAnalystState) -> dict:
    tickers_remaining = [
        t for t in state.get("tickers_to_analyze", [])
        if t not in state.get("ticker_analyses", {})
    ]
    if not tickers_remaining:
        return {}

    ticker = tickers_remaining[0]
    price_data = state.get("raw_prices", {}).get(ticker, {})
    news = state.get("raw_news", {}).get(ticker, [])
    sec_text = state.get("raw_filings", {}).get(ticker, "") or "Not available."

    # Generate source IDs for citation tracking
    price_source_id = _make_source_id("yfinance", ticker)
    fundamentals_source_id = _make_source_id("yfinance", ticker)
    indicators_source_id = _make_source_id("yfinance", ticker)
    news_source_id = _make_source_id("newsapi", ticker)
    sec_source_id = _make_source_id("sec_edgar", ticker)

    prompt = ANALYST_HUMAN.format(
        ticker=ticker,
        price_data=json.dumps(price_data.get("quote", {}), indent=2),
        price_source_id=price_source_id,
        fundamentals=json.dumps(price_data.get("fundamentals", {}), indent=2),
        fundamentals_source_id=fundamentals_source_id,
        indicators=json.dumps(price_data.get("indicators", {}), indent=2),
        indicators_source_id=indicators_source_id,
        article_count=len(news),
        news_text=_format_news(news),
        news_source_id=news_source_id,
        sec_notes=sec_text[:1500],
        sec_source_id=sec_source_id,
    )

    messages = [
        SystemMessage(content=ANALYST_SYSTEM),
        HumanMessage(content=prompt),
    ]

    response = await _get_llm().ainvoke(messages)

    # Try Pydantic validation first (structured output path)
    try:
        output = AnalysisOutput.model_validate_json(response.content)
    except (ValidationError, ValueError) as first_error:
        # Single retry: send validation errors back to model
        try:
            error_msg = str(first_error)[:500]
            retry_prompt = (
                f"Your JSON was invalid. Errors: {error_msg}\n"
                f"Fix the JSON and return a valid response matching the schema exactly."
            )
            retry_response = await _get_llm().ainvoke(
                messages + [HumanMessage(content=retry_prompt)]
            )
            output = AnalysisOutput.model_validate_json(retry_response.content)
        except (ValidationError, ValueError, Exception):
            # Fallback: use legacy extract_json for resilience
            try:
                parsed = extract_json(response.content)
                output = AnalysisOutput(
                    ticker=ticker,
                    signal=parsed.get("signal", "insufficient_data"),
                    confidence=parsed.get("confidence", "low"),
                    sentiment_score=float(parsed.get("sentiment_score", 0.0)),
                    thesis=parsed.get("thesis", parsed.get("news_summary", "")),
                    bull_case=parsed.get("bull_case", []),
                    bear_case=parsed.get("bear_case", []),
                    risk_flags=parsed.get("risk_flags", []),
                    citations=parsed.get("citations", []),
                    data_gaps=parsed.get("data_gaps", []),
                    price_data=price_data.get("quote", {}),
                    fundamentals=price_data.get("fundamentals", {}),
                    sec_notes=parsed.get("sec_notes", ""),
                    news_summary=parsed.get("news_summary", ""),
                )
            except (ValueError, KeyError, Exception):
                # Last resort: return insufficient_data
                output = AnalysisOutput(
                    ticker=ticker,
                    signal="insufficient_data",
                    confidence="low",
                    sentiment_score=0.0,
                    thesis="Analysis parsing failed. Insufficient structured data available.",
                    risk_flags=["Analysis parsing error"],
                    data_gaps=["LLM output validation failed"],
                    price_data=price_data.get("quote", {}),
                    fundamentals=price_data.get("fundamentals", {}),
                )

    # Convert to state-compatible TickerAnalysis dict
    analysis: TickerAnalysis = {
        "ticker": output.ticker,
        "signal": output.signal,
        "confidence": output.confidence,
        "sentiment_score": output.sentiment_score,
        "news_summary": output.news_summary or output.thesis,
        "risk_flags": output.risk_flags,
        "price_data": output.price_data or price_data.get("quote", {}),
        "fundamentals": output.fundamentals or price_data.get("fundamentals", {}),
        "sec_notes": output.sec_notes,
    }

    existing = dict(state.get("ticker_analyses", {}))
    existing[ticker] = analysis
    return {"ticker_analyses": existing, "current_ticker": ticker}
