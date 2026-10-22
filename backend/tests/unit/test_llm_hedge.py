"""Hedged primary attempts and the per-run attempt log."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agent import attempt_log, llm_fallback
from src.agent.llm_fallback import _hedged_invoke, _looks_like_json_object
from src.config import settings

VALID = AIMessage(content='{"signal": "hold", "confidence": "medium"}')


def _factory(delay, reply=None, error=None, log=None, name=""):
    async def _call():
        try:
            await asyncio.sleep(delay)
            if error is not None:
                raise error
            return reply if reply is not None else VALID
        except asyncio.CancelledError:
            if log is not None:
                log.append(f"{name}-cancelled")
            raise

    return _call


# --- reply validation ---


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"a": 1}', True),
        ('  {"a": 1}  ', True),
        ('{"a": 1', False),  # cut off at max_tokens
        ("", False),
        ("[1, 2]", False),
        ("plain text", False),
    ],
)
def test_only_complete_json_objects_count_as_a_valid_reply(content, expected):
    assert _looks_like_json_object(AIMessage(content=content)) is expected


# --- the race ---


@pytest.mark.asyncio
async def test_fast_primary_never_starts_the_hedge():
    started = []

    async def hedge():
        started.append(1)
        return VALID

    out = await _hedged_invoke(_factory(0.05), hedge, hedge_after=0.5)
    assert out.reasoning_off is False
    assert started == []


@pytest.mark.asyncio
async def test_stalled_primary_loses_to_the_hedge_and_is_cancelled():
    log: list[str] = []
    t0 = time.monotonic()
    out = await _hedged_invoke(
        _factory(30, log=log, name="primary"),
        _factory(0.1, log=log, name="hedge"),
        hedge_after=0.2,
    )
    assert out.reasoning_off is True
    assert time.monotonic() - t0 < 3
    assert "primary-cancelled" in log, "the losing stream must be cancelled, not left running"


@pytest.mark.asyncio
async def test_primary_that_lands_after_the_hedge_starts_still_wins_if_first():
    out = await _hedged_invoke(_factory(0.35), _factory(5), hedge_after=0.2)
    assert out.reasoning_off is False


@pytest.mark.asyncio
async def test_hedge_wins_when_the_primary_fails():
    out = await _hedged_invoke(
        _factory(0.3, error=RuntimeError("502 from provider")), _factory(0.2), hedge_after=0.1
    )
    assert out.reasoning_off is True


@pytest.mark.asyncio
async def test_primary_wins_when_the_hedge_fails():
    out = await _hedged_invoke(
        _factory(0.4), _factory(0.05, error=RuntimeError("hedge 429")), hedge_after=0.1
    )
    assert out.reasoning_off is False


@pytest.mark.asyncio
async def test_invalid_hedge_reply_does_not_win_the_race():
    truncated = AIMessage(content='{"signal": "ho')
    out = await _hedged_invoke(_factory(0.4), _factory(0.05, reply=truncated), hedge_after=0.1)
    assert out.reasoning_off is False
    assert _looks_like_json_object(out.result)


@pytest.mark.asyncio
async def test_both_failing_raises_the_primarys_error():
    with pytest.raises(RuntimeError, match="primary broke"):
        await _hedged_invoke(
            _factory(0.2, error=RuntimeError("primary broke")),
            _factory(0.1, error=RuntimeError("hedge broke")),
            hedge_after=0.05,
        )


@pytest.mark.asyncio
async def test_outer_cancellation_cancels_both_calls():
    log: list[str] = []
    task = asyncio.ensure_future(
        _hedged_invoke(
            _factory(30, log=log, name="primary"),
            _factory(30, log=log, name="hedge"),
            hedge_after=0.1,
        )
    )
    await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sorted(log) == ["hedge-cancelled", "primary-cancelled"]


# --- wiring into the chain ---


def _chain_patches(retry):
    def _fake_build(
        model, temperature, max_tokens, request_timeout, json_mode=True, reasoning_off=False
    ):
        m = AsyncMock()
        m._id = model
        m._off = reasoning_off
        return m

    return (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=retry),
        patch.object(type(settings), "llm_fallback_chain", property(lambda self: [])),
        patch.object(
            type(settings),
            "llm_reasoning_optional_set",
            property(lambda self: frozenset({"m-primary"})),
        ),
    )


@pytest.mark.asyncio
async def test_chain_hedges_the_primary_and_records_the_winner(monkeypatch):
    monkeypatch.setattr(settings, "llm_hedge_after_seconds", 0.1)

    async def _retry(llm, messages, *, breaker=None, deadline=None, **_kw):
        if llm._off:
            await asyncio.sleep(0.05)
            return VALID
        await asyncio.sleep(30)

    llm_fallback.answered_model.set(None)
    llm_fallback.answered_reasoning_off.set(False)
    p1, p2, p3, p4 = _chain_patches(_retry)
    with p1, p2, p3, p4:
        result = await llm_fallback.invoke_with_fallback(
            [], primary_model="m-primary", reasoning_off_on_fallback=True
        )

    assert result is VALID
    assert llm_fallback.answered_model.get() == "m-primary"
    assert llm_fallback.answered_reasoning_off.get() is True


@pytest.mark.asyncio
async def test_no_hedge_unless_the_caller_asked_for_rescue_mode(monkeypatch):
    monkeypatch.setattr(settings, "llm_hedge_after_seconds", 0.05)
    seen: list[bool] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None, **_kw):
        seen.append(llm._off)
        await asyncio.sleep(0.2)
        return VALID

    p1, p2, p3, p4 = _chain_patches(_retry)
    with p1, p2, p3, p4:
        await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    assert seen == [False]


@pytest.mark.asyncio
async def test_hedge_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "llm_hedge_after_seconds", 0)
    seen: list[bool] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None, **_kw):
        seen.append(llm._off)
        await asyncio.sleep(0.2)
        return VALID

    p1, p2, p3, p4 = _chain_patches(_retry)
    with p1, p2, p3, p4:
        await llm_fallback.invoke_with_fallback(
            [], primary_model="m-primary", reasoning_off_on_fallback=True
        )

    assert seen == [False]


def test_default_hedge_delay_is_later_than_most_completed_attempts():
    # 25s keeps the share of displaced ultra replies low; see the comment in config.
    assert settings.llm_hedge_after_seconds >= 20


# --- attempt log ---


def test_record_is_a_noop_without_an_active_run():
    attempt_log._attempts.set(None)
    attempt_log.record({"model": "x"})  # must not raise


def test_attempts_are_collected_per_run_with_the_current_role():
    bucket = attempt_log.start_run()
    attempt_log.set_role("bear")
    attempt_log.record({"model": "m", "outcome": "ok"})
    assert bucket == [{"role": "bear", "model": "m", "outcome": "ok"}]
    attempt_log._attempts.set(None)
    attempt_log.set_role(None)


def test_attempt_log_is_bounded():
    bucket = attempt_log.start_run()
    for i in range(attempt_log._MAX_ATTEMPTS + 25):
        attempt_log.record({"i": i})
    assert len(bucket) == attempt_log._MAX_ATTEMPTS
    attempt_log._attempts.set(None)


@pytest.mark.asyncio
async def test_invoke_with_retry_records_each_attempt():
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult

    class _Model(BaseChatModel):
        model: str = "rec-model"

        @property
        def _llm_type(self) -> str:
            return "rec"

        def _generate(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        async def _agenerate(self, messages, stop=None, run_manager=None, **kw):
            return ChatResult(generations=[ChatGeneration(message=VALID)])

    breaker = AsyncMock()

    async def _call(func, *a, **k):
        return await func(*a, **k)

    breaker.call = _call
    bucket = attempt_log.start_run()
    attempt_log.set_role("moderator")
    await llm_fallback._invoke_with_retry(_Model(), [], breaker=breaker)
    attempt_log._attempts.set(None)
    attempt_log.set_role(None)

    assert len(bucket) == 1
    entry = bucket[0]
    assert entry["role"] == "moderator" and entry["model"] == "rec-model"
    assert entry["outcome"] == "ok" and entry["mode"] == "reasoning_on"
    assert "content" not in entry and "prompt" not in entry
