"""
LLM invocation with model fallback chain.

On transient failures (ResourceExhausted, 429, 502, 503, timeout),
retries with the primary model first, then falls back to a secondary model.
Integrates with the existing circuit breaker and rate limiter.
"""

import asyncio
import contextvars
import logging
import os
import re
import time
from enum import Enum
from functools import lru_cache

from langchain_core.callbacks import AsyncCallbackHandler, BaseCallbackManager
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.runnables.config import ensure_config
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

# The chain clamps a model's slice to exactly the floor, and by the time the
# attempt starts a few milliseconds have passed, so the re-check inside
# _invoke_with_retry saw "7.99s < 8.0s" and aborted the whole chain with a
# non-fallback error instead of making the attempt. A small tolerance fixes the
# off-by-a-hair without letting a genuinely exhausted budget through.
_FLOOR_TOLERANCE_SECONDS = 0.5

# Model that produced the most recent successful response in this task. Read by
# callers (the debate node) to record which model actually answered a turn,
# since the configured primary is often not the one that did.
answered_model: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_answered_model", default=None
)


class _StreamStats(AsyncCallbackHandler):
    """Counts streamed chunks for one attempt so a slow call can be diagnosed.

    Reasoning models stream thinking chunks long before any content arrives, and
    some providers deliver the whole content in one chunk at the end, so first
    chunk and first content are tracked separately. The counters are updated
    live, which is what makes them readable after wait_for cancels the attempt.
    """

    raise_error = False

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.first_chunk_s: float | None = None
        self.first_content_s: float | None = None
        self.chunks = 0
        self.content_chars = 0

    async def on_llm_new_token(self, token: str, **kwargs) -> None:  # type: ignore[override]
        elapsed = time.monotonic() - self.started
        if self.first_chunk_s is None:
            self.first_chunk_s = elapsed
        self.chunks += 1
        if token:
            if self.first_content_s is None:
                self.first_content_s = elapsed
            self.content_chars += len(token)

    def describe(self) -> str:
        def _fmt(v: float | None) -> str:
            return "-" if v is None else f"{v:.1f}s"

        return (
            f"first_chunk={_fmt(self.first_chunk_s)} first_content={_fmt(self.first_content_s)} "
            f"chunks={self.chunks} content_chars={self.content_chars}"
        )


def _config_with_stats(stats: _StreamStats) -> dict:
    """Runnable config that adds the stats handler without displacing inherited ones.

    Passing callbacks=[stats] outright REPLACES the callbacks inherited from the
    surrounding run, which silently stops astream_events from seeing the model's
    events (token accounting and debate turn events depend on them). Merging into
    the inherited manager keeps them.
    """
    cfg = ensure_config()
    inherited = cfg.get("callbacks")
    if isinstance(inherited, BaseCallbackManager):
        merged = inherited.copy()
        merged.add_handler(stats, inherit=False)
        cfg["callbacks"] = merged
    else:
        cfg["callbacks"] = [*(inherited or []), stats]
    return dict(cfg)


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


def _is_stream_corruption(exc: BaseException) -> bool:
    """True for a malformed/truncated SSE-stream or JSON-decode transport error.

    The provider began streaming a response and then emitted a bad or truncated
    frame (bad JSON chunk, truncated SSE data, incomplete chunked read, peer
    closed mid-body). These are transient and usually worker/model-specific.

    Scope is deliberately narrow: only stream/SSE/chunk/decode-shaped wording
    matches. A bare "connection reset by peer" is intentionally NOT matched here
    (that stays RETRY_SAME_MODEL), and a plain schema/validation message with no
    stream/decode wording stays NOT_RETRYABLE. Auth/bad-request (400/401) is
    screened out earlier in _classify_error.
    """
    exc_str = str(exc).lower()
    stream_terms = (
        "sse",
        "stream",
        "chunk",
        "incomplete read",
        "incomplete chunked read",
        "peer closed",
        "response ended prematurely",
        "error injected",
    )
    decode_terms = ("decode", "parse", "expecting value", "unterminated")
    if any(t in exc_str for t in stream_terms):
        return True
    return "json" in exc_str and any(t in exc_str for t in decode_terms)


def _ratelimit_headers(exc: BaseException) -> dict[str, str]:
    """Pull OpenRouter's rate-limit headers off an openai SDK error, if present.

    openai.APIStatusError (the base of RateLimitError/APIError raised on a 429)
    carries the raw httpx response at exc.response, whose headers include
    OpenRouter's x-ratelimit-* and retry-after. These are the ONLY authoritative
    account-vs-host signal: the JSON body wording ("provider returned error" vs
    "rate limit exceeded") is unreliable, but x-ratelimit-remaining=0 with a
    reset far in the future is an unambiguous account-level daily/minute cap.

    Returns a lowercased-key dict (possibly empty) and never raises: a missing
    response, a non-mapping headers object, or any attribute error just yields
    {} so classification falls back to the string matcher. LangChain may also
    wrap the SDK error; we unwrap one level via __cause__/__context__.
    """
    for candidate in (exc, getattr(exc, "__cause__", None), getattr(exc, "__context__", None)):
        if candidate is None:
            continue
        response = getattr(candidate, "response", None)
        headers = getattr(response, "headers", None)
        if headers is None:
            continue
        try:
            return {str(k).lower(): str(v) for k, v in dict(headers).items()}
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue
    return {}


def _headers_show_account_cap(headers: dict[str, str]) -> bool:
    """True when rate-limit headers indicate the account-level allowance is spent.

    OpenRouter sends x-ratelimit-remaining (requests left in the current window)
    and x-ratelimit-reset (epoch-ms when it refills). remaining<=0 means the
    per-account free-tier window (e.g. the 50/day or 20/min cap) is exhausted, so
    every model on the account will 429 and walking the chain is futile. We do
    NOT gate on how far away the reset is: a spent window is spent regardless of
    whether it refills in seconds or hours, and the caller degrades either way.
    Absent/malformed headers return False so the string matcher still applies.
    """
    remaining = headers.get("x-ratelimit-remaining")
    if remaining is None:
        return False
    try:
        return float(remaining) <= 0
    except (TypeError, ValueError):
        return False


def _is_account_wide_throttle(exc: BaseException) -> bool:
    """True only for a 429 that applies to the whole OpenRouter ACCOUNT.

    OpenRouter distinguishes two 429s (verified against its own docs):

    - Account/global cap: body reads "rate limit exceeded" / "please slow down",
      or names a free-tier daily/per-minute allowance. This is governed globally
      per account, so EVERY model on the account 429s at once and walking the
      chain is futile - break and degrade in seconds.
    - Upstream passthrough: body reads "provider returned error". This is the
      UPSTREAM model host throttling, NOT the account. Different models route to
      different hosts, so the docs' own advice is "switch model / add a fallback
      route". That case is NOT matched here; it classifies as FALLBACK_TO_OTHER
      and walks the chain.

    A negative-credit-balance 429 (also account-scoped) is matched via the
    credit/insufficient markers so the chain does not thrash on an empty balance.
    """
    exc_str = str(exc).lower()
    if not re.search(r"\b429\b", exc_str):
        return False
    # Authoritative signal first: if OpenRouter's own rate-limit headers say the
    # account window is spent (x-ratelimit-remaining<=0), it is account-wide no
    # matter what the body text says - including the "provider returned error"
    # wording that would otherwise be treated as a per-host passthrough. The body
    # string is unreliable; the header is not.
    if _headers_show_account_cap(_ratelimit_headers(exc)):
        return True
    # Upstream passthrough is explicitly NOT an account-wide break: let it fall
    # through to FALLBACK_TO_OTHER so a different upstream host can be tried.
    if "provider returned error" in exc_str:
        return False
    return any(
        term in exc_str
        for term in (
            "rate limit exceeded",
            "please slow down",
            "free-tier",
            "free tier",
            "daily limit",
            "requests per day",
            "per-day",
            "insufficient credit",
            "negative credit",
            "negative balance",
            "add more credits",
        )
    )


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

    # 404 from the upstream host ("Function ... Not found for account", or a
    # free variant that was withdrawn) is specific to this model route. Another
    # model in the chain can still serve the request, so walk on instead of
    # failing the whole turn on a dead primary.
    if re.search(r"\b404\b", exc_str):
        return ErrorSeverity.FALLBACK_TO_OTHER

    # OpenRouter can identify a shared upstream pool limit explicitly. That
    # means another model/provider is more useful than retrying this route.
    if "upstream_provider_shared_pool" in exc_str or "shared pool" in exc_str:
        return ErrorSeverity.FALLBACK_TO_OTHER

    # Upstream-provider passthrough 429 ("provider returned error"): the model's
    # upstream host throttled, not our account. All chain models are free-variant
    # models on one account, so they share the same congested free pool - walking
    # straight to a sibling is NOT reliably better, it is just as likely to 429.
    # These congestion windows are typically seconds long, so a short same-model
    # jittered backoff (handled by the tenacity retry on _invoke_with_retry:
    # wait_exponential 2-10s, 2 attempts, DEADLINE-GATED so it can never overrun
    # the per-turn budget) clears most of them. RETRY_SAME_MODEL is also
    # fallback-worthy, so if the brief retry still fails the chain is walked after
    # - giving a second free model a chance in case its upstream is distinct.
    # (Panel-ratified over immediate chain-walk: the free pool is shared, so a
    # bounded wait beats thrashing every sibling against the same hot upstream.)
    # NOTE: an account-global 429 ("rate limit exceeded" / daily cap / negative
    # balance) is handled by the chain short-circuit via _is_account_wide_throttle,
    # which runs in invoke_with_fallback before classification; it is not matched
    # here.
    if re.search(r"\b429\b", exc_str) and "provider returned error" in exc_str:
        return ErrorSeverity.RETRY_SAME_MODEL

    if "rate limit" in exc_str and any(term in exc_str for term in ("temporarily", "temporary")):
        return ErrorSeverity.RETRY_SAME_MODEL

    # A generic 429 may be a short-lived throttle: retry once on the same
    # model. Text-only rate-limit errors without a status code are treated as
    # route-specific and sent to the fallback model.
    if re.search(r"\b429\b", exc_str):
        return ErrorSeverity.RETRY_SAME_MODEL
    if "rate limit" in exc_str or "rate_limit" in exc_str:
        return ErrorSeverity.FALLBACK_TO_OTHER

    # Upstream provider capacity: try a different model
    if "resource" in exc_str and "exhausted" in exc_str:
        return ErrorSeverity.FALLBACK_TO_OTHER
    if re.search(r"\b(502|503)\b", exc_str):
        return ErrorSeverity.FALLBACK_TO_OTHER
    if "timeout" in exc_str:
        return ErrorSeverity.FALLBACK_TO_OTHER
    if "overloaded" in exc_str:
        return ErrorSeverity.FALLBACK_TO_OTHER
    # Transport/stream-decode failures: the provider began streaming an SSE
    # response and then emitted a malformed or truncated chunk (bad JSON frame,
    # truncated SSE data, incomplete chunked read, peer closed mid-body). These
    # surface as an openai.APIError whose message carries none of the numeric
    # status tokens above, so without this branch they fall through to
    # NOT_RETRYABLE and nuke the whole turn on the primary. They are transient
    # and often model/worker-specific, so route to a DIFFERENT provider rather
    # than hammering the same stream that just broke. See _is_stream_corruption
    # for the (deliberately narrow) matching rules.
    if _is_stream_corruption(exc):
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

    # Other transient server failures can succeed on a quick retry.
    if re.search(r"\b500\b", exc_str):
        return ErrorSeverity.RETRY_SAME_MODEL
    if any(term in exc_str for term in ("connection", "temporar", "unavailable")):
        return ErrorSeverity.RETRY_SAME_MODEL

    return ErrorSeverity.NOT_RETRYABLE


def _is_retryable_error(exc: BaseException) -> bool:
    """Return True for errors worth retrying on the same model.

    FALLBACK_TO_OTHER errors (CircuitBreakerOpen, ResourceExhausted) are NOT
    retried here — retrying the same broken model wastes time. They bubble up
    to invoke_with_fallback which routes to a different model.

    An account-wide upstream throttle (see _is_account_wide_throttle) is also
    excluded: a bare 429 normally classifies as RETRY_SAME_MODEL, but when the
    429 is the account-wide free-tier throttle, even one same-model retry just
    burns backoff time on a limit that a few seconds will not clear. It bubbles
    straight to the chain handler, which short-circuits.
    """
    if _is_account_wide_throttle(exc):
        return False
    return _classify_error(exc) == ErrorSeverity.RETRY_SAME_MODEL


def _is_fallback_worthy(exc: BaseException) -> bool:
    """Return True for errors where trying a different model might help.

    Both FALLBACK_TO_OTHER (immediate fallback) and RETRY_SAME_MODEL (after
    retries are exhausted) should trigger fallback. Only NOT_RETRYABLE errors
    (auth failures, bad requests) should never fall back.
    """
    return _classify_error(exc) != ErrorSeverity.NOT_RETRYABLE


@lru_cache(maxsize=32)
def _build_llm(
    model: str,
    temperature: float,
    max_tokens: int,
    request_timeout: int,
    json_mode: bool = True,
    reasoning_off: bool = False,
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
        # OpenRouter's switch for the hidden thinking phase. Only ever set for
        # models listed in settings.llm_reasoning_optional_models.
        extra_body={"reasoning": {"enabled": False}} if reasoning_off else None,
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
    reasoning_off_on_fallback: bool = False,
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
        reasoning_off_on_fallback: When True, fallback attempts (not the primary)
            on models that allow it run with reasoning disabled. The primary always
            keeps full reasoning; this only makes a rescue fast enough to land in
            the small slice a timed-out primary leaves behind.
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
        reasoning_off = (
            reasoning_off_on_fallback
            and not is_primary
            and model in settings.llm_reasoning_optional_set
        )
        llm = _build_llm(
            model,
            temperature,
            max_tokens,
            request_timeout,
            effective_json_mode,
            reasoning_off=reasoning_off,
        )
        runnable: ChatOpenAI | Runnable = llm.bind_tools(tools) if tools else llm
        try:
            result = await _invoke_with_retry(
                runnable, messages, breaker=breaker, deadline=model_deadline
            )
            answered_model.set(model)
            if not is_primary:
                log.info(
                    "fallback_model_succeeded model=%s position=%d reasoning=%s",
                    model,
                    index,
                    "off" if reasoning_off else "on",
                )
            return result
        except Exception as exc:
            last_exc = exc
            # Account-wide upstream throttle: every model on the chain shares one
            # account/base_url, so a free-tier account 429 hits them all at once.
            # Walking the chain here only burns the per-turn budget on repeated
            # backoff until the deadline trips. Short-circuit so the turn degrades
            # in seconds. Counted on the ops dashboard
            # (/ops/metrics -> counters.llm_account_throttles_total).
            if _is_account_wide_throttle(exc):
                try:
                    from src.metrics import metrics as _metrics

                    _metrics.inc("llm_account_throttles_total", labels={"model": model})
                except Exception:  # pragma: no cover - defensive
                    pass
                log.warning(
                    "llm_account_throttle model=%s position=%d error=%s - "
                    "short-circuiting chain (all models share one throttled account)",
                    model,
                    index,
                    str(exc)[:100],
                )
                break
            # Observability: count malformed/truncated SSE-stream decode failures
            # so they surface on the ops dashboard (/ops/metrics ->
            # counters.llm_stream_corruptions_total, labelled by model). This is
            # the transient class the stream-decode branch of _classify_error
            # routes to FALLBACK_TO_OTHER; tracking it distinguishes "provider is
            # emitting broken frames" from ordinary 429/timeout fallbacks.
            # Best-effort: a metrics failure must never break the LLM path.
            if _classify_error(exc) is ErrorSeverity.FALLBACK_TO_OTHER and _is_stream_corruption(
                exc
            ):
                try:
                    from src.metrics import metrics as _metrics

                    _metrics.inc("llm_stream_corruptions_total", labels={"model": model})
                except Exception:  # pragma: no cover - defensive
                    pass
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
        if remaining < floor - _FLOOR_TOLERANCE_SECONDS:
            raise TimeoutError(
                f"LLM attempt budget exhausted: {remaining:.1f}s remaining < {floor:.1f}s floor"
            )
        effective_timeout = min(cap, remaining)
    else:
        effective_timeout = cap

    stats = _StreamStats()
    model = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    try:
        result = await asyncio.wait_for(
            breaker.call(llm.ainvoke, messages, config=_config_with_stats(stats)),
            timeout=effective_timeout,
        )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        log.warning(
            "llm_attempt_timeout model=%s after=%.0fs %s",
            model,
            effective_timeout,
            stats.describe(),
        )
        raise TimeoutError(
            f"LLM attempt exceeded {effective_timeout:.0f}s wall-clock timeout (model={model})"
        ) from exc

    meta = getattr(result, "response_metadata", None)
    finish = meta.get("finish_reason") if isinstance(meta, dict) else None
    log.info(
        "llm_attempt_ok model=%s elapsed=%.1fs finish=%s %s",
        model,
        time.monotonic() - stats.started,
        finish,
        stats.describe(),
    )
    return result
