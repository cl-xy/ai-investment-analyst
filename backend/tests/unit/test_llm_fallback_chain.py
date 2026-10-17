"""Tests for the multi-model fallback chain.

When both the primary and the first fallback are unavailable (primary stalls,
fallback hit by an upstream shared-pool 429), invoke_with_fallback must keep
walking the chain to a healthy model from a different provider instead of
failing the whole run.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agent import llm_fallback
from src.config import settings


def test_shared_pool_429_routes_to_other_model():
    """A shared-pool 429 is a provider-capacity signal, not a retry-same-model one."""
    body = (
        "Error code: 429 - google/gemma-4-31b-it:free is temporarily rate-limited "
        "upstream ... limit_source: upstream_provider_shared_pool"
    )
    exc = Exception(body)
    assert llm_fallback._classify_error(exc) is llm_fallback.ErrorSeverity.FALLBACK_TO_OTHER


def test_plain_429_still_retries_same_model():
    """A bare 429 with no shared-pool signal keeps the retry-same-model behavior."""
    exc = Exception("Error code: 429 - too many requests")
    assert llm_fallback._classify_error(exc) is llm_fallback.ErrorSeverity.RETRY_SAME_MODEL


def test_malformed_sse_stream_routes_to_other_model():
    """A malformed/truncated JSON chunk mid-SSE-stream is a transient transport
    failure, not a permanent one: it must route to a different provider instead
    of falling through to NOT_RETRYABLE and nuking the whole turn.

    Regression: a live CELH debate run failed with
    'Debate failed: bull agent error (APIError)' /
    'Bull agent failed: JSON error injected into SSE stream' because this exact
    error string matched none of the numeric status patterns and classified as
    NOT_RETRYABLE, so no same-model retry and no fallback model ever ran.
    """
    for body in (
        "APIError: JSON error injected into SSE stream",
        "openai.APIError: error while parsing stream chunk: Expecting value",
        "peer closed connection without sending complete message body (incomplete chunked read)",
        "json decode error: unterminated string in SSE data",
    ):
        exc = Exception(body)
        assert llm_fallback._classify_error(exc) is llm_fallback.ErrorSeverity.FALLBACK_TO_OTHER, (
            f"expected FALLBACK_TO_OTHER for: {body!r}"
        )


def test_schema_and_auth_errors_stay_not_retryable():
    """The new stream/decode branch must not swallow genuinely permanent errors.

    A 400/401 is still NOT_RETRYABLE even if the message happens to mention JSON
    (the auth check runs first), and a plain schema/validation message with no
    stream/decode wording also stays NOT_RETRYABLE.
    """
    assert (
        llm_fallback._classify_error(Exception("Error code: 400 - invalid json schema"))
        is llm_fallback.ErrorSeverity.NOT_RETRYABLE
    )
    assert (
        llm_fallback._classify_error(Exception("response did not match the expected schema"))
        is llm_fallback.ErrorSeverity.NOT_RETRYABLE
    )


def test_fallback_chain_is_ordered_and_deduped():
    """The configured chain parses into an ordered, de-duplicated model list."""
    chain = settings.llm_fallback_chain
    assert chain, "fallback chain must not be empty"
    assert len(chain) == len(set(chain)), "fallback chain must have no duplicates"
    # Primary is prepended inside invoke_with_fallback; it should not also appear here.
    assert settings.llm_model not in chain


def test_is_stream_corruption_narrow_scope():
    """The helper only matches stream/SSE/chunk/decode wording, not bare
    connection resets or plain schema errors."""
    assert llm_fallback._is_stream_corruption(Exception("JSON error injected into SSE stream"))
    assert llm_fallback._is_stream_corruption(Exception("error parsing stream chunk"))
    assert llm_fallback._is_stream_corruption(Exception("json decode error: unterminated string"))
    # Not stream-shaped:
    assert not llm_fallback._is_stream_corruption(Exception("connection reset by peer"))
    assert not llm_fallback._is_stream_corruption(Exception("429 too many requests"))
    assert not llm_fallback._is_stream_corruption(Exception("response did not match schema"))


@pytest.mark.asyncio
async def test_stream_corruption_increments_metric():
    """When a model fails mid-stream, the ops counter is incremented with the
    failing model label so the corruption surfaces on /ops/metrics, and the
    chain still falls over to a healthy model."""
    from src.metrics import metrics

    before = metrics.llm_stream_corruptions_total.get(labels={"model": "m-primary"})

    async def _retry(llm, messages, *, breaker=None, deadline=None):
        model = getattr(llm, "_model_id", "unknown")
        if model == "m-primary":
            raise Exception("APIError: JSON error injected into SSE stream")
        return "ok-from-fallback"

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(
            type(settings),
            "llm_fallback_chain",
            property(lambda self: ["m-fallback-1"]),
        ),
    ):
        result = await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    assert result == "ok-from-fallback"
    after = metrics.llm_stream_corruptions_total.get(labels={"model": "m-primary"})
    assert after == before + 1


@pytest.mark.asyncio
async def test_non_stream_fallback_does_not_increment_stream_metric():
    """An ordinary overloaded/timeout fallback must NOT bump the stream-corruption
    counter - the metric is specific to malformed-stream failures."""
    from src.metrics import metrics

    before = metrics.llm_stream_corruptions_total.get(labels={"model": "m-primary"})

    async def _retry(llm, messages, *, breaker=None, deadline=None):
        model = getattr(llm, "_model_id", "unknown")
        if model == "m-primary":
            raise Exception("model is overloaded, please retry")
        return "ok"

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(
            type(settings),
            "llm_fallback_chain",
            property(lambda self: ["m-fallback-1"]),
        ),
    ):
        result = await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    assert result == "ok"
    after = metrics.llm_stream_corruptions_total.get(labels={"model": "m-primary"})
    assert after == before


@pytest.mark.asyncio
async def test_chain_walks_all_fallbacks_until_success():
    """With an explicit multi-model chain, each dead model is skipped in order."""
    attempted: list[str] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None):
        model = getattr(llm, "_model_id", "unknown")
        attempted.append(model)
        if model in ("m-primary", "m-a", "m-b"):
            raise Exception("overloaded")  # fallback-worthy
        return "ok"

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(
            type(settings),
            "llm_fallback_chain",
            property(lambda self: ["m-a", "m-b", "m-c"]),
        ),
    ):
        result = await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    assert result == "ok"
    assert attempted == ["m-primary", "m-a", "m-b", "m-c"]


@pytest.mark.asyncio
async def test_not_retryable_error_aborts_chain_immediately():
    """An auth error must not walk the chain; it fails fast."""
    attempted: list[str] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None):
        attempted.append(getattr(llm, "_model_id", "unknown"))
        raise Exception("Error code: 401 - unauthorized")

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(
            type(settings),
            "llm_fallback_chain",
            property(lambda self: ["m-a", "m-b"]),
        ),
    ):
        with pytest.raises(Exception, match="401"):
            await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    # Only the primary was tried; a non-retryable error does not walk the chain.
    assert attempted == ["m-primary"]


@pytest.mark.asyncio
async def test_deadline_stops_chain_before_exhausting_all_models(monkeypatch):
    """With almost no budget left, the chain stops early and raises an ordinary
    Exception (not CancelledError) so the caller can build a degraded partial."""
    import time as _time

    attempted: list[str] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None):
        attempted.append(getattr(llm, "_model_id", "unknown"))
        # Consume most of the budget on each attempt so the deadline is reached
        # after the first model or two, not all five.
        import asyncio as _asyncio

        await _asyncio.sleep(0.3)
        raise Exception("overloaded")  # fallback-worthy

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    # Shrink the floor so the sub-second test budget behaves like production.
    monkeypatch.setattr(llm_fallback, "_MIN_USEFUL_ATTEMPT_SECONDS", 0.2)
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 0.4)
    deadline = _time.monotonic() + 0.6

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(
            type(settings),
            "llm_fallback_chain",
            property(lambda self: ["m-a", "m-b", "m-c", "m-d"]),
        ),
    ):
        with pytest.raises(Exception):
            await llm_fallback.invoke_with_fallback(
                [], primary_model="m-primary", deadline=deadline
            )

    # Did NOT walk all 5 models; stopped once budget was spent.
    assert len(attempted) < 5


@pytest.mark.asyncio
async def test_deadline_reserves_budget_so_a_fallback_still_starts(monkeypatch):
    """A slow-failing primary must NOT consume the whole turn budget: the chain
    reserves a floor so at least one fallback model gets a real attempt. This is
    the core fix - previously the primary ate the budget and no fallback ran."""
    import asyncio as _asyncio
    import time as _time

    attempted: list[str] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None):
        model = getattr(llm, "_model_id", "unknown")
        attempted.append(model)
        if model == "m-primary":
            # Primary burns its whole slice then fails (slow-but-erroring).
            now = _time.monotonic()
            if deadline is not None:
                await _asyncio.sleep(max(deadline - now, 0.0))
            raise TimeoutError("LLM attempt exceeded wall-clock timeout (model=m-primary)")
        return "ok-from-fallback"  # first fallback succeeds

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    # Floor 0.2s, total budget 2s. The primary is capped at budget - reserve, so
    # ~0.2s is held back for the fallback, which is >= floor and thus runs.
    monkeypatch.setattr(llm_fallback, "_MIN_USEFUL_ATTEMPT_SECONDS", 0.2)
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 5.0)
    deadline = _time.monotonic() + 2.0

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(
            type(settings),
            "llm_fallback_chain",
            property(lambda self: ["m-fallback-1", "m-fallback-2"]),
        ),
    ):
        result = await llm_fallback.invoke_with_fallback(
            [], primary_model="m-primary", deadline=deadline
        )

    # The primary did not starve the chain: a fallback actually ran and won.
    assert result == "ok-from-fallback"
    assert attempted[0] == "m-primary"
    assert "m-fallback-1" in attempted


@pytest.mark.asyncio
async def test_deadline_threaded_as_monotonic_instant(monkeypatch):
    """invoke_with_fallback passes _invoke_with_retry a monotonic deadline
    instant (not a scalar timeout), capped below the overall deadline so a
    tenacity re-entry can re-read the clock."""
    import time as _time

    seen_deadlines: list[float | None] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None):
        seen_deadlines.append(deadline)
        return "ok"  # primary succeeds immediately

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 45.0)
    overall_deadline = _time.monotonic() + 20.0

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
    ):
        result = await llm_fallback.invoke_with_fallback(
            [], primary_model="m-primary", deadline=overall_deadline
        )

    assert result == "ok"
    assert seen_deadlines and seen_deadlines[0] is not None
    # The per-model deadline must not exceed the overall deadline.
    assert seen_deadlines[0] <= overall_deadline + 0.01


@pytest.mark.asyncio
async def test_no_deadline_passes_none():
    """Without a deadline, _invoke_with_retry receives deadline=None (configured
    default timeout applies). Preserves behaviour for callers like chat.py."""
    seen: list[float | None] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None):
        seen.append(deadline)
        return "ok"

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
    ):
        result = await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    assert result == "ok"
    assert seen == [None]


@pytest.mark.asyncio
async def test_invoke_with_retry_fails_fast_below_floor(monkeypatch):
    """_invoke_with_retry raises immediately (does NOT start a doomed attempt)
    when the remaining budget is below the floor, so a tenacity re-entry or a
    tight chain slice cannot kick off a call that cannot finish."""
    import time as _time

    monkeypatch.setattr(llm_fallback, "_MIN_USEFUL_ATTEMPT_SECONDS", 8.0)
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 45.0)

    started = {"called": False}

    class _LLM:
        model = "m-x"

        async def ainvoke(self, _messages):
            started["called"] = True
            return "nope"

    # Deadline only 1s away; floor is 8s -> fail fast without calling ainvoke.
    near_deadline = _time.monotonic() + 1.0

    with pytest.raises(TimeoutError):
        await llm_fallback._invoke_with_retry(
            _LLM(), [], breaker=llm_fallback.llm_breaker, deadline=near_deadline
        )

    assert started["called"] is False


@pytest.mark.asyncio
async def test_invoke_with_retry_caps_attempt_to_remaining_budget(monkeypatch):
    """When a deadline is set, the attempt's wall-clock timeout is capped to the
    remaining budget, not the configured 45s ceiling."""
    import asyncio as _asyncio
    import time as _time

    monkeypatch.setattr(llm_fallback, "_MIN_USEFUL_ATTEMPT_SECONDS", 0.1)
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 45.0)

    class _HangingLLM:
        model = "m-hang"

        async def ainvoke(self, _messages):
            await _asyncio.sleep(10.0)  # would exceed the capped timeout
            return "nope"

    # ~0.3s of budget: the attempt must be cancelled well before 45s.
    deadline = _time.monotonic() + 0.3
    t0 = _time.monotonic()

    with pytest.raises(TimeoutError):
        await llm_fallback._invoke_with_retry(
            _HangingLLM(), [], breaker=llm_fallback.llm_breaker, deadline=deadline
        )

    elapsed = _time.monotonic() - t0
    assert elapsed < 2.0  # capped by remaining budget, not the 45s default


def test_account_wide_throttle_detection():
    """Only a genuine ACCOUNT-global 429 is a chain-break; an upstream-provider
    passthrough 429 is NOT (it should walk to a different model).

    OpenRouter distinguishes two 429s: 'rate limit exceeded / please slow down'
    (account-global cap, governed per-account so every model 429s at once) vs
    'provider returned error' (the upstream model host throttled, which differs
    per model). Only the former justifies short-circuiting the chain.
    """
    # Account-global cap and negative balance → break the chain.
    assert llm_fallback._is_account_wide_throttle(
        Exception("Error code: 429 - Rate limit exceeded. Please slow down.")
    )
    assert llm_fallback._is_account_wide_throttle(Exception("429 free-tier daily limit reached"))
    assert llm_fallback._is_account_wide_throttle(
        Exception("Error code: 429 - negative credit balance, add more credits")
    )
    # Upstream passthrough is explicitly NOT a chain-break (must walk the chain).
    assert not llm_fallback._is_account_wide_throttle(
        Exception(
            "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429}}"
        )
    )
    # Not a 429 at all
    assert not llm_fallback._is_account_wide_throttle(Exception("503 service unavailable"))


def test_upstream_passthrough_429_retries_same_model_then_fallback():
    """The live CELH error - 429 'Provider returned error' - classifies as
    RETRY_SAME_MODEL: a short deadline-gated same-model backoff clears most
    seconds-long free-pool congestion windows, and because RETRY_SAME_MODEL is
    still fallback-worthy, the chain is walked afterwards if it keeps failing.

    (Panel-ratified over immediate chain-walk: all chain models share one
    congested free pool, so a bounded wait beats thrashing every sibling against
    the same hot upstream. Budget overrun is prevented by the deadline-gated
    tenacity retry, not by skipping the retry.)
    """
    exc = Exception(
        "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429}}"
    )
    assert llm_fallback._classify_error(exc) is llm_fallback.ErrorSeverity.RETRY_SAME_MODEL
    # Retryable on the same model (bounded backoff), AND fallback-worthy (walks
    # the chain if the retry still fails).
    assert llm_fallback._is_retryable_error(exc) is True
    assert llm_fallback._is_fallback_worthy(exc) is True
    # It is NOT an account-global short-circuit (that path is for the daily/RPM
    # cap, not an upstream host blip).
    assert llm_fallback._is_account_wide_throttle(exc) is False


@pytest.mark.asyncio
async def test_upstream_passthrough_429_walks_chain_to_healthy_model():
    """On a 'provider returned error' 429, the chain must try the next distinct
    model (a different upstream host may succeed) rather than short-circuit."""
    attempted: list[str] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None):
        model = getattr(llm, "_model_id", "unknown")
        attempted.append(model)
        if model == "m-primary":
            raise Exception("Error code: 429 - Provider returned error, code 429")
        return "ok-from-fallback"

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(
            type(settings),
            "llm_fallback_chain",
            property(lambda self: ["m-a", "m-b"]),
        ),
    ):
        result = await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    # Walked to the first fallback and succeeded; did NOT short-circuit.
    assert result == "ok-from-fallback"
    assert attempted == ["m-primary", "m-a"]


@pytest.mark.asyncio
async def test_account_global_429_short_circuits_chain():
    """An ACCOUNT-global 429 ('rate limit exceeded') must short-circuit: every
    model shares the throttled account, so walking the chain only burns the turn
    budget. Only the first model is tried; the ops counter is incremented."""
    from src.metrics import metrics

    before = metrics.llm_account_throttles_total.get(labels={"model": "m-primary"})
    attempted: list[str] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None):
        attempted.append(getattr(llm, "_model_id", "unknown"))
        raise Exception("Error code: 429 - Rate limit exceeded. Please slow down.")

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(
            type(settings),
            "llm_fallback_chain",
            property(lambda self: ["m-a", "m-b", "m-c", "m-d"]),
        ),
    ):
        with pytest.raises(Exception, match="429"):
            await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    assert attempted == ["m-primary"]
    after = metrics.llm_account_throttles_total.get(labels={"model": "m-primary"})
    assert after == before + 1
