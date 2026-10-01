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

    async def _retry(llm, messages, *, breaker=None):
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

    async def _retry(llm, messages, *, breaker=None):
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
