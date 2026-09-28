import asyncio
import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.logging_config import get_logger

from ..llm_fallback import invoke_with_fallback
from ..prompts.report_prompt import REPORT_HUMAN, REPORT_SYSTEM
from ..state import InvestmentAnalystState

log = get_logger(__name__)

# Narrative synthesis is supplementary: ticker analyses have already been
# validated and checkpointed by this point. Keep this deliberately shorter than
# the request-wide budget so a slow provider cannot turn a completed analysis
# into a failed run.
REPORT_GENERATION_TIMEOUT = 45


def _report_input(analyses: dict) -> list[dict]:
    """Return the compact, report-relevant portion of each ticker analysis."""
    fields = (
        "ticker",
        "signal",
        "confidence",
        "sentiment_score",
        "thesis",
        "news_summary",
        "bull_case",
        "bear_case",
        "risk_flags",
        "data_gaps",
        "price_data",
        "fundamentals",
        "earnings",
    )
    result = []
    for analysis in analyses.values():
        if not isinstance(analysis, dict):
            continue
        # Citation payloads and SEC excerpts can be very large. They remain
        # available on the ticker card, but are not needed to write the report.
        result.append({field: analysis[field] for field in fields if field in analysis})
    return result


def _fallback_report(analyses: dict) -> str:
    """Create a useful deterministic summary if optional LLM synthesis is unavailable."""
    lines = [
        "## Executive Summary",
        "Individual ticker analyses completed. Narrative report synthesis was unavailable.",
        "",
        "## Signal Summary",
        "| Ticker | Signal | Confidence | Sentiment |",
        "| --- | --- | --- | --- |",
    ]
    for ticker, analysis in analyses.items():
        lines.append(
            "| {ticker} | {signal} | {confidence} | {sentiment} |".format(
                ticker=ticker,
                signal=analysis.get("signal", "N/A"),
                confidence=analysis.get("confidence", "N/A"),
                sentiment=analysis.get("sentiment_score", "N/A"),
            )
        )
    lines.extend(
        [
            "",
            "## Recommended Actions",
            "Review the completed ticker cards, including their risks and source evidence, before making investment decisions.",
        ]
    )
    return "\n".join(lines)


async def generate_report_node(state: InvestmentAnalystState) -> dict:
    analyses = state.get("ticker_analyses", {})
    portfolio = state.get("portfolio", [])
    correlation_id = state.get("correlation_id")
    _log = (
        log.bind(correlation_id=correlation_id, node="generate_report") if correlation_id else log
    )

    if not analyses:
        return {"report_markdown": "No ticker analyses available to generate a report."}

    try:
        portfolio_context = ""
        if portfolio:
            lines = ["Current holdings:"]
            for pos in portfolio:
                lines.append(
                    f"  - {pos['ticker']}: {pos['shares']} shares @ ${pos['cost_basis']:.2f} (sector: {pos.get('sector', 'Unknown')})"
                )
            portfolio_context = "\n".join(lines)
        else:
            portfolio_context = "No portfolio loaded. Analyzing requested tickers only."

        prompt = REPORT_HUMAN.format(
            analyses_json=json.dumps(_report_input(analyses), indent=2),
            portfolio_context=portfolio_context,
        )

        response = await asyncio.wait_for(
            invoke_with_fallback(
                [
                    SystemMessage(content=REPORT_SYSTEM),
                    HumanMessage(content=prompt),
                ],
                temperature=0,
                max_tokens=1200,
                request_timeout=REPORT_GENERATION_TIMEOUT,
                json_mode=False,
            ),
            timeout=REPORT_GENERATION_TIMEOUT,
        )
    except asyncio.TimeoutError:
        _log.warning("generate_report_timed_out", timeout_seconds=REPORT_GENERATION_TIMEOUT)
        return {
            "report_markdown": _fallback_report(analyses),
            "report_status": "timed_out",
        }
    except Exception as e:
        _log.warning("generate_report_failed", error=str(e), exc_info=True)
        return {
            "report_markdown": _fallback_report(analyses),
            "report_status": "failed",
        }

    # Normalize content: some providers return list of content blocks instead of str
    content = response.content
    if isinstance(content, list):
        content = "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return {"report_markdown": content, "report_status": "generated"}
