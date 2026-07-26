import json
import os
from functools import cache

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from ..prompts.report_prompt import REPORT_HUMAN, REPORT_SYSTEM
from ..state import InvestmentAnalystState


@cache
def _get_llm() -> ChatOpenAI:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set")
    return ChatOpenAI(
        model="llama-3.3-70b-versatile",
        temperature=0,
        max_tokens=4096,
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
    )


async def generate_report_node(state: InvestmentAnalystState) -> dict:
    analyses = state.get("ticker_analyses", {})
    portfolio = state.get("portfolio", [])

    portfolio_context = ""
    if portfolio:
        lines = ["Current holdings:"]
        for pos in portfolio:
            lines.append(f"  - {pos['ticker']}: {pos['shares']} shares @ ${pos['cost_basis']:.2f} (sector: {pos.get('sector', 'Unknown')})")
        portfolio_context = "\n".join(lines)
    else:
        portfolio_context = "No portfolio loaded — analyzing requested tickers only."

    prompt = REPORT_HUMAN.format(
        analyses_json=json.dumps(list(analyses.values()), indent=2),
        portfolio_context=portfolio_context,
    )

    response = await _get_llm().ainvoke([
        SystemMessage(content=REPORT_SYSTEM),
        HumanMessage(content=prompt),
    ])

    return {"report_markdown": response.content}
