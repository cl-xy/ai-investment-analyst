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
from langchain_openai import ChatOpenAI
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .circuit_breaker import CircuitBreakerOpen, llm_breaker

log = logging.getLogger(__name__)


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
    if any(code in exc_str for code in ("401", "400", "unauthorized", "bad request")):
        return ErrorSeverity.NOT_RETRYABLE

    # Upstream provider capacity: try a different model
    if "resourceexhausted" in exc_str:
        return ErrorSeverity.FALLBACK_TO_OTHER
    if any(code in exc_str for code in ("502", "503")):
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
    """Return True for errors where trying a different model might help."""
    return _classify_error(exc) == ErrorSeverity.FALLBACK_TO_OTHER


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
    """
    from ..config import settings

    primary = primary_model or settings.llm_model
    fallback = fallback_model or settings.llm_model_fallback

    # Try primary model
    primary_llm = _build_llm(primary, temperature, max_tokens, request_timeout, json_mode)
    try:
        return await _invoke_with_retry(primary_llm, messages)
    except Exception as primary_exc:
        if not _is_fallback_worthy(primary_exc):
            raise

        log.warning(
            "primary_model_failed model=%s error=%s, trying fallback=%s",
            primary,
            str(primary_exc)[:100],
            fallback,
        )

    # Try fallback model
    fallback_llm = _build_llm(fallback, temperature, max_tokens, request_timeout, json_mode)
    try:
        result = await _invoke_with_retry(fallback_llm, messages)
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
async def _invoke_with_retry(llm: ChatOpenAI, messages: list) -> BaseMessage:
    """Invoke a specific LLM instance with retry, through the circuit breaker."""
    return await llm_breaker.call(llm.ainvoke, messages)  # type: ignore[return-value]
