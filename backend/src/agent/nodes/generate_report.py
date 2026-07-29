import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

log = logging.getLogger(__name__)

from ..llm_fallback import invoke_with_fallback
from ..prompts.report_prompt import REPORT_HUMAN, REPORT_SYSTEM
from ..state import InvestmentAnalystState


async def generate_report_node(state: InvestmentAnalystState) -> dict:
    analyses = state.get("ticker_analyses", {})
    portfolio = state.get("portfolio", [])

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
        log.warning("generate_report_node LLM call failed: %s", e)
        return {
            "report_markdown": "Analysis complete but report generation failed. Please review individual ticker analyses above."
        }

    return {"report_markdown": response.content}
