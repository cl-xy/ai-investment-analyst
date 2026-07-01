import os
from functools import cache

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from ..json_utils import extract_json
from ..prompts.router_prompt import ROUTER_HUMAN, ROUTER_SYSTEM
from ..state import InvestmentAnalystState


@cache
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="llama-3.1-8b-instant",
        temperature=0,
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
    )


async def router_node(state: InvestmentAnalystState) -> dict:
    # If intent was pre-set by the caller (e.g. CLI with known command), skip LLM routing
    if state.get("intent"):
        return {}

    last_message = state["messages"][-1]
    user_text = last_message.content if hasattr(last_message, "content") else str(last_message)

    response = await _get_llm().ainvoke([
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=ROUTER_HUMAN.format(message=user_text)),
    ])

    try:
        parsed = extract_json(response.content)
        intent = parsed.get("intent", "conversational")
        tickers = [t.upper() for t in parsed.get("tickers", [])]
    except (ValueError, AttributeError):
        intent = "conversational"
        tickers = []

    return {"intent": intent, "tickers_to_analyze": tickers}
