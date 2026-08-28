"""
LLM drift judge (Tier 2 of the alert evaluation pipeline).

Only invoked when the heuristic scorer (drift_scorer.py) flags a ticker as
"likely changed." Uses a single cheap call to the fast router model (not the
120B debate model) to answer a narrow question: given the prior thesis and
what's new, would the investment verdict actually change?

Budget-gated: if the OpenRouter daily budget is exhausted, callers should
fall back to a heuristic-only alert (see composer.py) rather than blocking
or crashing the evaluation pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError, field_validator

from src.agent.json_utils import extract_json
from src.agent.llm_fallback import invoke_with_fallback
from src.alerts.last_analysis import LastAnalysisSnapshot
from src.alerts.triggers.events import TriggerEvent
from src.cache.budget import use_budget
from src.logging_config import get_logger

log = get_logger(__name__)

_JUDGE_TEMPERATURE = 0.0
_JUDGE_MAX_TOKENS = 1024
_JUDGE_TIMEOUT = 30  # seconds — this must stay fast, it's not the main debate


class DriftJudgment(BaseModel):
    """Structured verdict from the drift judge LLM call."""

    changed: bool = Field(description="Whether the investment verdict would likely change")
    new_signal: str = Field(default="", description="buy|hold|sell if changed, else empty")
    reasoning: str = Field(default="", description="1-2 sentence explanation")
    key_shifts: list[str] = Field(
        default_factory=list, description="Specific arguments/facts that shifted"
    )

    @field_validator("new_signal", mode="before")
    @classmethod
    def _normalize_signal(cls, v: object) -> str:
        if not isinstance(v, str):
            return ""
        normalized = v.strip().lower()
        return normalized if normalized in ("buy", "hold", "sell") else ""

    @field_validator("key_shifts", mode="before")
    @classmethod
    def _coerce_key_shifts(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(item) for item in v if item]


@dataclass(frozen=True, slots=True)
class JudgeResult:
    """Outcome of attempting to invoke the LLM judge. `judgment` is None when
    the call was skipped (budget exhausted) or failed — callers must handle
    both by falling back to a heuristic-only alert."""

    judgment: DriftJudgment | None
    llm_invoked: bool
    skip_reason: str | None = field(default=None)


_SYSTEM_PROMPT = """You are a fast triage judge for an investment analysis system. \
You are given a prior investment thesis and a short list of things that changed \
since it was written. Decide whether the verdict (buy/hold/sell) would likely be \
different if the analysis were redone today.

Be conservative: only say the verdict changed if the shifts are clearly material \
to the thesis, not just noise. Respond with ONLY a JSON object, no prose, matching:
{"changed": bool, "new_signal": "buy"|"hold"|"sell"|"", "reasoning": str, "key_shifts": [str]}
"""


def _build_human_prompt(
    ticker: str, snapshot: LastAnalysisSnapshot, events: list[TriggerEvent]
) -> str:
    changes = (
        "\n".join(f"- {e.summary}" for e in events)
        or "- (no specific events; heuristic score alone triggered this check)"
    )
    risk_flags = ", ".join(snapshot.risk_flags) if snapshot.risk_flags else "none recorded"
    return (
        f"Ticker: {ticker}\n"
        f"Prior signal: {snapshot.signal} (confidence: {snapshot.confidence})\n"
        f"Prior sentiment score: {snapshot.sentiment_score:.2f}\n"
        f"Prior risk flags: {risk_flags}\n\n"
        f"What changed since then:\n{changes}\n\n"
        "Would the verdict change? Respond with the JSON object only."
    )


async def judge_drift(
    ticker: str,
    snapshot: LastAnalysisSnapshot,
    events: list[TriggerEvent],
) -> JudgeResult:
    """Ask the LLM whether the heuristic-flagged drift is material enough to
    change the verdict. Checks OpenRouter budget before calling."""
    budget_ok = await use_budget("openrouter")
    if not budget_ok:
        log.warning("drift_judge_skipped_budget_exhausted ticker=%s", ticker)
        return JudgeResult(judgment=None, llm_invoked=False, skip_reason="budget_exhausted")

    from src.config import settings

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_build_human_prompt(ticker, snapshot, events)),
    ]

    try:
        response = await invoke_with_fallback(
            messages,
            primary_model=settings.llm_router_model,
            fallback_model=settings.llm_router_model_fallback,
            temperature=_JUDGE_TEMPERATURE,
            max_tokens=_JUDGE_MAX_TOKENS,
            request_timeout=_JUDGE_TIMEOUT,
            json_mode=True,
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        parsed = extract_json(content)
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
        judgment = DriftJudgment.model_validate(parsed)
        return JudgeResult(judgment=judgment, llm_invoked=True)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        log.warning("drift_judge_parse_failed ticker=%s error=%s", ticker, exc)
        return JudgeResult(judgment=None, llm_invoked=True, skip_reason="parse_failed")
    except Exception as exc:
        log.warning("drift_judge_llm_failed ticker=%s error=%s", ticker, exc)
        return JudgeResult(judgment=None, llm_invoked=True, skip_reason="llm_call_failed")
