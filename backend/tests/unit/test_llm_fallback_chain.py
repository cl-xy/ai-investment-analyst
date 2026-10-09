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


def test_fallback_chain_is_ordered_and_deduped():
    """The configured chain parses into an ordered, de-duplicated model list."""
    chain = settings.llm_fallback_chain
    assert chain, "fallback chain must not be empty"
    assert len(chain) == len(set(chain)), "fallback chain must have no duplicates"
    # Primary is prepended inside invoke_with_fallback; it should not also appear here.
    assert settings.llm_model not in chain


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
