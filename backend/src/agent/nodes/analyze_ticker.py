import json
import os
from functools import cache

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from ..json_utils import extract_json
from ..prompts.analyst_prompt import ANALYST_HUMAN, ANALYST_SYSTEM
from ..state import InvestmentAnalystState, TickerAnalysis


@cache
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="llama-3.3-70b-versatile",
        temperature=0,
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
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

    prompt = ANALYST_HUMAN.format(
        ticker=ticker,
        price_data=json.dumps(price_data.get("quote", {}), indent=2),
        fundamentals=json.dumps(price_data.get("fundamentals", {}), indent=2),
        indicators=json.dumps(price_data.get("indicators", {}), indent=2),
        article_count=len(news),
        news_text=_format_news(news),
        sec_notes=sec_text[:1500],
    )

    response = await _get_llm().ainvoke([
        SystemMessage(content=ANALYST_SYSTEM),
        HumanMessage(content=prompt),
    ])

    try:
        parsed = extract_json(response.content)
        analysis: TickerAnalysis = {
            "ticker": ticker,
            "signal": parsed.get("signal", "insufficient_data"),
            "confidence": parsed.get("confidence", "low"),
            "sentiment_score": float(parsed.get("sentiment_score", 0.0)),
            "news_summary": parsed.get("news_summary", ""),
            "risk_flags": parsed.get("risk_flags", []),
            "price_data": price_data.get("quote", {}),
            "fundamentals": price_data.get("fundamentals", {}),
            "sec_notes": parsed.get("sec_notes", ""),
        }
    except (ValueError, KeyError):
        analysis = {
            "ticker": ticker,
            "signal": "insufficient_data",
            "confidence": "low",
            "sentiment_score": 0.0,
            "news_summary": response.content[:500],
            "risk_flags": ["Analysis parsing error"],
            "price_data": price_data.get("quote", {}),
            "fundamentals": price_data.get("fundamentals", {}),
            "sec_notes": "",
        }

    existing = dict(state.get("ticker_analyses", {}))
    existing[ticker] = analysis
    return {"ticker_analyses": existing, "current_ticker": ticker}
