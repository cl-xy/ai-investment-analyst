"""Tests for the hard wall-clock timeout on LLM attempts.

ChatOpenAI's request_timeout is only an httpx inter-chunk read timeout, so a
trickling free-tier stream never trips it. _invoke_with_retry wraps each attempt
in asyncio.wait_for to enforce a real deadline, converting a hung stream into a
TimeoutError that routes to the fallback model.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.agent import llm_fallback
from src.config import settings


@pytest.mark.asyncio
async def test_invoke_with_retry_aborts_hung_stream(monkeypatch):
    """A call that never returns is aborted at the wall-clock deadline, not left to hang."""
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 0.2)

    async def _hang(*_args, **_kwargs):
        await asyncio.sleep(60)  # simulate a trickling stream that never completes

    breaker = AsyncMock()
    breaker.call = AsyncMock(side_effect=_hang)

    fake_llm = AsyncMock()

    start = asyncio.get_event_loop().time()
    with pytest.raises(TimeoutError):
        await llm_fallback._invoke_with_retry(fake_llm, [], breaker=breaker)
    elapsed = asyncio.get_event_loop().time() - start

    # Aborted at ~0.2s, not left to hang for 60s.
    assert elapsed < 5.0


def test_timeout_error_routes_to_fallback():
    """A wall-clock TimeoutError must be classified as fallback-worthy."""
    exc = TimeoutError("LLM attempt exceeded 60s wall-clock timeout (model=x)")
    assert llm_fallback._is_fallback_worthy(exc) is True
    assert llm_fallback._classify_error(exc) is llm_fallback.ErrorSeverity.FALLBACK_TO_OTHER


@pytest.mark.asyncio
async def test_hung_primary_falls_back_to_secondary(monkeypatch):
    """When the primary model hangs, the fallback model is invoked and its result returned."""
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 0.2)

    calls: list[str] = []

    async def _retry(llm, messages, *, breaker=None):
        name = getattr(llm, "_name", "unknown")
        calls.append(name)
        if name == "primary":
            raise TimeoutError("LLM attempt exceeded 0s wall-clock timeout (model=primary)")
        return "fallback-result"

    primary = AsyncMock()
    primary._name = "primary"
    fallback = AsyncMock()
    fallback._name = "fallback"

    def _fake_build(model, *_a, **_k):
        return primary if "super" in model else fallback

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
    ):
        result = await llm_fallback.invoke_with_fallback(
            [],
            primary_model="nvidia/nemotron-3-super-120b-a12b:free",
            fallback_model="nvidia/nemotron-3-nano-30b-a3b:free",
        )

    assert result == "fallback-result"
    assert calls == ["primary", "fallback"]
