import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.logging_config import get_logger

log = get_logger(__name__)

from ..llm_fallback import invoke_with_fallback
from ..prompts.report_prompt import REPORT_HUMAN, REPORT_SYSTEM
from ..state import InvestmentAnalystState


async def generate_report_node(state: InvestmentAnalystState) -> dict:
    analyses = state.get("ticker_analyses", {})
    portfolio = state.get("portfolio", [])
    correlation_id = state.get("correlation_id")
    _log = (
        log.bind(correlation_id=correlation_id, node="generate_report") if correlation_id else log
    )

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
        analyses_json=json.dumps(list(analyses.values()), indent=2),
        portfolio_context=portfolio_context,
    )

    try:
        response = await invoke_with_fallback(
            [
                SystemMessage(content=REPORT_SYSTEM),
                HumanMessage(content=prompt),
            ],
            temperature=0,
            max_tokens=8192,
            request_timeout=120,
            json_mode=False,
        )
    except Exception as e:
        _log.warning("generate_report_failed", error=str(e))
        return {
            "report_markdown": "Analysis complete but report generation failed. Please review individual ticker analyses above."
        }

    return {"report_markdown": response.content}
