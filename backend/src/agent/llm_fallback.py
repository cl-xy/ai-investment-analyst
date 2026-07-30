"""
LLM invocation with model fallback chain.

On transient failures (ResourceExhausted, 429, 502, 503, timeout),
retries with the primary model first, then falls back to a secondary model.
Integrates with the existing circuit breaker and rate limiter.
"""

import logging
import os
import re
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

# Separate breaker for fallback model so primary failures don't block fallback.
# Uses the same shared rate limiter (llm_limiter) inside CircuitBreaker.call().
_fallback_breaker = CircuitBreaker(
    name="llm_fallback",
    failure_threshold=5,
    window_seconds=60.0,
    recovery_seconds=30.0,
)


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

    # Rate limit or transient: retry same model first
    if re.search(r"\b(429|500)\b", exc_str):
        return ErrorSeverity.RETRY_SAME_MODEL
    if "rate limit" in exc_str:
        return ErrorSeverity.RETRY_SAME_MODEL
    if any(term in exc_str for term in ("connection", "temporary", "unavailable")):
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
) -> BaseMessage:
    """
    Invoke LLM with retry + fallback chain.

    1. Try primary model with exponential backoff (2 attempts)
    2. If primary fails with a fallback-worthy error, try fallback model (2 attempts)
    3. If both fail, raise the last exception

    Args:
        messages: Chat messages to send
        primary_model: Primary model ID (defaults to settings.llm_model)
        fallback_model: Fallback model ID (defaults to settings.llm_model_fallback)
        temperature: LLM temperature
        max_tokens: Max output tokens
        request_timeout: Request timeout in seconds
        json_mode: Whether to request JSON output format
        tools: Optional tools to bind to the model (for tool-calling loops).
            Applied to both the primary and fallback model on every call, since
            bound runnables aren't cacheable the same way as the bare client.
    """
    from ..config import settings

    primary = primary_model or settings.llm_model
    fallback = fallback_model or settings.llm_model_fallback

    # Disable json_mode when tools are provided: OpenAI rejects requests
    # combining response_format=json_object with tool definitions.
    effective_json_mode = json_mode and not tools

    # Try primary model
    primary_llm = _build_llm(primary, temperature, max_tokens, request_timeout, effective_json_mode)
    primary_runnable: ChatOpenAI | Runnable = (
        primary_llm.bind_tools(tools) if tools else primary_llm
    )
    try:
        return await _invoke_with_retry(primary_runnable, messages, breaker=llm_breaker)
    except Exception as primary_exc:
        if not _is_fallback_worthy(primary_exc):
            raise

        log.warning(
            "primary_model_failed model=%s error=%s, trying fallback=%s",
            primary,
            str(primary_exc)[:100],
            fallback,
        )

    # Try fallback model (uses separate breaker so primary failures don't block it)
    fallback_llm = _build_llm(fallback, temperature, max_tokens, request_timeout, effective_json_mode)
    fallback_runnable: ChatOpenAI | Runnable = (
        fallback_llm.bind_tools(tools) if tools else fallback_llm
    )
    try:
        result = await _invoke_with_retry(
            fallback_runnable, messages, breaker=_fallback_breaker
        )
        log.info("fallback_model_succeeded model=%s", fallback)
        return result
    except Exception as fallback_exc:
        log.error(
            "fallback_model_failed model=%s error=%s",
            fallback,
            str(fallback_exc)[:100],
        )
        raise


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
) -> BaseMessage:
    """Invoke a specific LLM instance with retry, through the given circuit breaker."""
    return await breaker.call(llm.ainvoke, messages)  # type: ignore[return-value]
