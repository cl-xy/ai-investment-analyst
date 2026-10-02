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

    async def _retry(llm, messages, *, breaker=None, attempt_timeout=None):
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

    async def _retry(llm, messages, *, breaker=None, attempt_timeout=None):
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

    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 45.0)
    attempted: list[str] = []

    async def _retry(llm, messages, *, breaker=None, attempt_timeout=None):
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

    # ~0.5s of budget with a sub-second floor: the primary runs, then the loop
    # sees too little remaining and stops instead of walking all models.
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 0.4)
    deadline = _time.monotonic() + 0.5

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
async def test_deadline_passes_shrinking_attempt_timeout(monkeypatch):
    """Each model's attempt_timeout is capped by the remaining budget."""
    import time as _time

    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 45.0)
    seen_timeouts: list[float | None] = []

    async def _retry(llm, messages, *, breaker=None, attempt_timeout=None):
        seen_timeouts.append(attempt_timeout)
        return "ok"  # primary succeeds immediately

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._model_id = model
        return m

    # 20s of budget: attempt_timeout should be min(45, ~20) = ~20, not 45.
    deadline = _time.monotonic() + 20.0

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
    ):
        result = await llm_fallback.invoke_with_fallback(
            [], primary_model="m-primary", deadline=deadline
        )

    assert result == "ok"
    assert seen_timeouts and seen_timeouts[0] is not None
    assert seen_timeouts[0] <= 20.5  # capped by remaining budget, not the 45s default


@pytest.mark.asyncio
async def test_no_deadline_passes_none_attempt_timeout():
    """Without a deadline, attempt_timeout is None (use the configured default)."""
    seen: list[float | None] = []

    async def _retry(llm, messages, *, breaker=None, attempt_timeout=None):
        seen.append(attempt_timeout)
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
