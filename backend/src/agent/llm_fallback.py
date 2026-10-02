"""
LLM invocation with model fallback chain.

On transient failures (ResourceExhausted, 429, 502, 503, timeout),
retries with the primary model first, then falls back to a secondary model.
Integrates with the existing circuit breaker and rate limiter.
"""

import asyncio
import logging
import os
import re
import time
from enum import Enum
from functools import lru_cache

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpen, llm_breaker

log = logging.getLogger(__name__)

# Smallest remaining wall-clock budget worth starting a model attempt with.
# A healthy free-tier reasoning call completes in ~35-45s, so this is NOT a
# "healthy call fits" threshold; it is the point below which even a fast-failing
# or cached response cannot land. Used in two places that must agree: the chain
# loop reserves this much for the NEXT model so a slow primary cannot consume
# the whole turn budget, and _invoke_with_retry fails fast below it so a tenacity
# re-entry cannot start a doomed attempt.
_MIN_USEFUL_ATTEMPT_SECONDS = 8.0

# Separate breaker for fallback model so primary failures don't block fallback.
# Uses the same shared rate limiter (llm_limiter) inside CircuitBreaker.call().
_fallback_breaker = CircuitBreaker(
    name="llm_fallback",
    failure_threshold=5,
    window_seconds=60.0,
    recovery_seconds=30.0,
)

# One breaker per fallback model id. A single shared fallback breaker would let
# one saturated provider's 429s trip the breaker for a different, healthy
# fallback model. Independent breakers keep each model's health isolated.
_fallback_breakers: dict[str, CircuitBreaker] = {}


def _breaker_for(model: str) -> CircuitBreaker:
    """Return a per-model circuit breaker, creating one on first use."""
    breaker = _fallback_breakers.get(model)
    if breaker is None:
        breaker = CircuitBreaker(
            name=f"llm_fallback:{model}",
            failure_threshold=5,
            window_seconds=60.0,
            recovery_seconds=30.0,
        )
        _fallback_breakers[model] = breaker
    return breaker


class ErrorSeverity(Enum):
    """Classification of LLM call errors for retry/fallback decisions."""

    NOT_RETRYABLE = "not_retryable"
    RETRY_SAME_MODEL = "retry_same_model"
    FALLBACK_TO_OTHER = "fallback_to_other"


def _classify_error(exc: BaseException) -> ErrorSeverity:
    """Classify an exception to determine retry/fallback strategy."""
    # Circuit breaker open means primary is failing repeatedly
    if isinstance(exc, CircuitBreakerOpen):
        return ErrorSeverity.FALLBACK_TO_OTHER

    exc_str = str(exc).lower()

    # Auth/bad request: don't retry at all
    if re.search(r"\b(401|400)\b", exc_str) or any(
        term in exc_str for term in ("unauthorized", "bad request")
    ):
        return ErrorSeverity.NOT_RETRYABLE

    # Upstream provider capacity: try a different model
    if "resource" in exc_str and "exhausted" in exc_str:
        return ErrorSeverity.FALLBACK_TO_OTHER
    if re.search(r"\b(502|503)\b", exc_str):
        return ErrorSeverity.FALLBACK_TO_OTHER
    if "timeout" in exc_str:
        return ErrorSeverity.FALLBACK_TO_OTHER
    if "overloaded" in exc_str:
        return ErrorSeverity.FALLBACK_TO_OTHER
    # A 429 caused by the provider's shared free-tier pool being saturated
    # (limit_source=upstream_provider_shared_pool) will not clear in a 2-10s
    # retry window: retrying the same congested model just burns the budget.
    # Route to a different provider immediately instead.
    if re.search(r"\b429\b", exc_str) and any(
        term in exc_str
        for term in ("shared_pool", "shared pool", "upstream_provider", "temporarily rate-limited")
    ):
        return ErrorSeverity.FALLBACK_TO_OTHER

    # Rate limit or transient: retry same model first
    if re.search(r"\b(429|500)\b", exc_str):
        return ErrorSeverity.RETRY_SAME_MODEL
    if "rate limit" in exc_str:
        return ErrorSeverity.RETRY_SAME_MODEL
    if any(term in exc_str for term in ("connection", "temporar", "unavailable")):
        return ErrorSeverity.RETRY_SAME_MODEL

    return ErrorSeverity.NOT_RETRYABLE


def _is_retryable_error(exc: BaseException) -> bool:
    """Return True for errors worth retrying on the same model.

    FALLBACK_TO_OTHER errors (CircuitBreakerOpen, ResourceExhausted) are NOT
    retried here — retrying the same broken model wastes time. They bubble up
    to invoke_with_fallback which routes to a different model.
    """
    return _classify_error(exc) == ErrorSeverity.RETRY_SAME_MODEL


def _is_fallback_worthy(exc: BaseException) -> bool:
    """Return True for errors where trying a different model might help.

    Both FALLBACK_TO_OTHER (immediate fallback) and RETRY_SAME_MODEL (after
    retries are exhausted) should trigger fallback. Only NOT_RETRYABLE errors
    (auth failures, bad requests) should never fall back.
    """
    return _classify_error(exc) != ErrorSeverity.NOT_RETRYABLE


@lru_cache(maxsize=8)
def _build_llm(
    model: str,
    temperature: float,
    max_tokens: int,
    request_timeout: int,
    json_mode: bool = True,
) -> ChatOpenAI:
    """Build a cached ChatOpenAI instance for the given model config."""
    from ..config import settings

    api_key = settings.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable is not set")

    kwargs: dict = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,  # type: ignore[call-arg]
        base_url=settings.llm_base_url,
        api_key=api_key,  # type: ignore[arg-type]
        model_kwargs=kwargs,
        request_timeout=request_timeout,  # type: ignore[call-arg]
    )


async def invoke_with_fallback(
    messages: list,
    *,
    primary_model: str | None = None,
    fallback_model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 16384,
    request_timeout: int = 120,
    json_mode: bool = True,
    tools: list | None = None,
    deadline: float | None = None,
) -> BaseMessage:
    """
    Invoke LLM with a multi-model retry + fallback chain.

    1. Try the primary model with exponential backoff (2 attempts).
    2. On a fallback-worthy error, walk the ordered fallback chain, trying each
       model (2 attempts each) until one succeeds. The chain spans distinct
       upstream providers so a single provider's shared-pool 429 does not take
       down every option.
    3. If the whole chain fails, raise the last exception so the caller can
       degrade gracefully.

    Args:
        messages: Chat messages to send
        primary_model: Primary model ID (defaults to settings.llm_model)
        fallback_model: If given, used as the sole fallback (back-compat).
            Otherwise the full settings.llm_fallback_chain is used.
        temperature: LLM temperature
        max_tokens: Max output tokens
        request_timeout: Request timeout in seconds
        json_mode: Whether to request JSON output format
        tools: Optional tools to bind to the model (for tool-calling loops).
            Applied to every model on every call, since bound runnables aren't
            cacheable the same way as the bare client.
        deadline: Optional monotonic (time.monotonic()) wall-clock deadline for
            the WHOLE chain. Without it, every per-attempt timeout on a dead
            provider stacks up (5 models x 45s = ~3.75 min) and can outlive the
            caller's own budget, so the caller is cancelled mid-call and never
            gets to build its degraded result. With it, we stop walking the
            chain once too little time remains for a useful attempt and raise
            the last error as an ordinary Exception, which the caller's
            try/except can turn into a graceful partial.
    """
    from ..config import settings

    primary = primary_model or settings.llm_model
    if fallback_model is not None:
        fallbacks = [fallback_model]
    else:
        fallbacks = settings.llm_fallback_chain
    # The primary leads the chain; de-dupe so it isn't retried as a fallback.
    chain: list[str] = [primary] + [m for m in fallbacks if m != primary]

    # Disable json_mode when tools are provided: OpenAI rejects requests
    # combining response_format=json_object with tool definitions.
    effective_json_mode = json_mode and not tools

    last_exc: BaseException | None = None
    n_models = len(chain)
    for index, model in enumerate(chain):
        # Per-model deadline. The key move: when a deadline is set and models
        # remain after this one, cap THIS model so it cannot consume the whole
        # remaining budget and starve every fallback. We reserve a small slice
        # for the next model (see below), guaranteeing it actually gets a real
        # attempt instead of being skipped by the "too little time left" gate.
        # Without a deadline, every model gets the full configured timeout
        # (unchanged for callers like chat.py).
        model_deadline: float | None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining < _MIN_USEFUL_ATTEMPT_SECONDS:
                log.warning(
                    "llm_chain_deadline model=%s remaining=%.1fs floor=%.1fs",
                    model,
                    remaining,
                    _MIN_USEFUL_ATTEMPT_SECONDS,
                )
                break
            models_left_after = n_models - index - 1
            # Reserve slightly MORE than one floor for the next model (not one
            # per remaining model): the goal is that at least one fallback gets a
            # real attempt if this model fails fast, WITHOUT starving a healthy
            # 35-45s primary. The 1.5x margin absorbs the handling jitter between
            # the primary failing and the next model's start gate, so the
            # reserved time doesn't dip below the floor and skip the fallback.
            # Capped at half the budget so we never reserve more than we keep.
            # Two full healthy calls genuinely cannot both fit in a ~50s turn;
            # this guarantees a fallback on fast-fail, which is the common
            # free-tier case (429 / circuit-open / connection reset).
            reserve = (
                min(_MIN_USEFUL_ATTEMPT_SECONDS * 1.5, remaining / 2.0)
                if models_left_after
                else 0.0
            )
            this_budget = max(remaining - reserve, _MIN_USEFUL_ATTEMPT_SECONDS)
            model_deadline = time.monotonic() + this_budget
            log.info(
                "llm_chain_slice model=%s position=%d remaining=%.1fs this_budget=%.1fs reserved=%.1fs",
                model,
                index,
                remaining,
                this_budget,
                reserve,
            )
        else:
            model_deadline = None

        is_primary = index == 0
        breaker = llm_breaker if is_primary else _breaker_for(model)
        llm = _build_llm(model, temperature, max_tokens, request_timeout, effective_json_mode)
        runnable: ChatOpenAI | Runnable = llm.bind_tools(tools) if tools else llm
        try:
            result = await _invoke_with_retry(
                runnable, messages, breaker=breaker, deadline=model_deadline
            )
            if not is_primary:
                log.info("fallback_model_succeeded model=%s position=%d", model, index)
            return result
        except Exception as exc:
            last_exc = exc
            # Auth/bad-request style errors won't be fixed by another model.
            if not _is_fallback_worthy(exc):
                raise
            next_model = chain[index + 1] if index + 1 < len(chain) else None
            if next_model is not None:
                log.warning(
                    "llm_model_failed model=%s error=%s, trying next=%s",
                    model,
                    str(exc)[:100],
                    next_model,
                )
            else:
                log.error(
                    "llm_chain_exhausted last_model=%s error=%s",
                    model,
                    str(exc)[:100],
                )

    # Whole chain failed (or ran out of budget).
    if last_exc is not None:
        raise last_exc
    raise TimeoutError("invoke_with_fallback: model chain budget exhausted before any attempt")


@retry(
    retry=retry_if_exception(_is_retryable_error),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(2),
    reraise=True,
)
async def _invoke_with_retry(
    llm: "ChatOpenAI | Runnable",
    messages: list,
    *,
    breaker: "CircuitBreaker" = llm_breaker,
    deadline: float | None = None,
) -> BaseMessage:
    """Invoke a specific LLM instance with retry, through the given circuit breaker.

    Wrapped in a hard wall-clock timeout: ChatOpenAI's request_timeout is only an
    httpx inter-chunk read timeout, so a slow free-tier stream that emits an
    occasional token or keepalive never trips it and the call hangs for minutes.
    asyncio.wait_for enforces a real deadline per attempt. On timeout we raise a
    TimeoutError, which _classify_error routes to FALLBACK_TO_OTHER so the
    fallback model is tried instead of the whole run budget being consumed.

    deadline, when given, is a monotonic wall-clock instant the WHOLE call
    (including any tenacity same-model retry) must finish by. It is re-read on
    every entry, so a second tenacity attempt cannot reuse a stale per-attempt
    budget and run another full timeout + backoff past the caller's deadline:
    each attempt is capped at min(configured_timeout, deadline - now), and if
    too little remains we fail fast so the enclosing chain can try a different
    model or degrade. Without a deadline, the configured ceiling applies and
    behaviour is unchanged for other callers (e.g. chat.py).
    """
    from ..config import settings

    cap = settings.llm_attempt_timeout_seconds
    if deadline is not None:
        remaining = deadline - time.monotonic()
        # Floor below which an attempt (or retry) cannot usefully complete.
        floor = min(cap, _MIN_USEFUL_ATTEMPT_SECONDS)
        if remaining < floor:
            raise TimeoutError(
                f"LLM attempt budget exhausted: {remaining:.1f}s remaining < {floor:.1f}s floor"
            )
        effective_timeout = min(cap, remaining)
    else:
        effective_timeout = cap

    try:
        return await asyncio.wait_for(
            breaker.call(llm.ainvoke, messages),  # type: ignore[return-value]
            timeout=effective_timeout,
        )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        model = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
        log.warning(
            "llm_attempt_timeout model=%s after=%.0fs",
            model,
            effective_timeout,
        )
        raise TimeoutError(
            f"LLM attempt exceeded {effective_timeout:.0f}s wall-clock timeout (model={model})"
        ) from exc
