from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from src.logging_config import get_logger

from ..json_utils import extract_json
from ..llm_fallback import invoke_with_fallback
from ..prompts.router_prompt import ROUTER_HUMAN, ROUTER_SYSTEM
from ..state import InvestmentAnalystState
from ..structured_output import RouterOutput

log = get_logger(__name__)

_VALID_INTENTS = frozenset(RouterOutput.model_fields["intent"].annotation.__args__)


async def router_node(state: InvestmentAnalystState) -> dict:
    # If intent was pre-set by the caller (e.g. CLI with known command), skip LLM routing
    if state.get("intent"):
        return {}

    correlation_id = state.get("correlation_id")
    _log = log.bind(correlation_id=correlation_id, node="router") if correlation_id else log

    from ...config import settings

    last_message = state["messages"][-1]
    # Handle both string content and list-of-blocks (multimodal) content
    raw_content = last_message.content if hasattr(last_message, "content") else str(last_message)
    if isinstance(raw_content, list):
        # Extract text from content blocks
        user_text = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in raw_content
        )
    else:
        user_text = str(raw_content) if raw_content is not None else ""

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
        _log.warning("router_llm_failed", error=str(e))
        return {"intent": "conversational", "tickers_to_analyze": []}

    # Try structured validation first
    try:
        content = response.content
        if not isinstance(content, (str, bytes)):
            raise TypeError(f"Expected str/bytes content, got {type(content).__name__}")
        output = RouterOutput.model_validate_json(content)
        intent = output.intent
        tickers = [t.upper() for t in output.tickers]
    except (ValidationError, ValueError, TypeError):
        # Fallback to legacy extraction
        try:
            parsed = extract_json(response.content if isinstance(response.content, str) else "")
            raw_intent = parsed.get("intent", "conversational")
            # Validate intent against allowed values
            intent = raw_intent if raw_intent in _VALID_INTENTS else "conversational"
            raw_tickers = parsed.get("tickers") or []
            # Guard against tickers being a string (would iterate chars)
            if isinstance(raw_tickers, str):
                raw_tickers = [raw_tickers]
            tickers = [t.upper() for t in raw_tickers if isinstance(t, str) and t.strip()]
        except (ValueError, AttributeError, TypeError):
            intent = "conversational"
            tickers = []

    return {"intent": intent, "tickers_to_analyze": tickers}
