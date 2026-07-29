import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

log = logging.getLogger(__name__)

from ..json_utils import extract_json
from ..llm_fallback import invoke_with_fallback
from ..prompts.router_prompt import ROUTER_HUMAN, ROUTER_SYSTEM
from ..state import InvestmentAnalystState
from ..structured_output import RouterOutput


async def router_node(state: InvestmentAnalystState) -> dict:
    # If intent was pre-set by the caller (e.g. CLI with known command), skip LLM routing
    if state.get("intent"):
        return {}

    from ...config import settings

    last_message = state["messages"][-1]
    user_text = last_message.content if hasattr(last_message, "content") else str(last_message)

    try:
        # Rate limiting is handled by the circuit breaker inside invoke_with_fallback
        response = await invoke_with_fallback(
            [
                SystemMessage(content=ROUTER_SYSTEM),
                HumanMessage(content=ROUTER_HUMAN.format(message=user_text)),
            ],
            primary_model=settings.llm_router_model,
            fallback_model=settings.llm_router_model_fallback,
            temperature=0.0,
            max_tokens=256,
            request_timeout=30,
        )
    except Exception as e:
        log.warning("router_node LLM call failed: %s", e)
        return {"intent": "conversational", "tickers_to_analyze": []}

    # Try structured validation first
    try:
        output = RouterOutput.model_validate_json(response.content)
        intent = output.intent
        tickers = [t.upper() for t in output.tickers]
    except (ValidationError, ValueError):
        # Fallback to legacy extraction
        try:
            parsed = extract_json(response.content)
            intent = parsed.get("intent", "conversational")
            raw_tickers = parsed.get("tickers") or []
            tickers = [t.upper() for t in raw_tickers if isinstance(t, str)]
        except (ValueError, AttributeError, TypeError):
            intent = "conversational"
            tickers = []

    return {"intent": intent, "tickers_to_analyze": tickers}
