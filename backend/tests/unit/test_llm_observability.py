"""Streaming diagnostics, floor tolerance, answered-model tracking, chain order."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableLambda

from src.agent import llm_fallback
from src.config import settings


class _FakeStreamingModel(BaseChatModel):
    """Streams n tokens with a small delay, like a provider would."""

    n_tokens: int = 6
    delay: float = 0.02
    model: str = "fake-model"

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, *a, **k):  # pragma: no cover - sync path unused
        raise NotImplementedError

    async def _agenerate(self, messages, stop=None, run_manager=None, **kw):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="full"))])

    async def _astream(self, messages, stop=None, run_manager=None, **kw):
        for i in range(self.n_tokens):
            await asyncio.sleep(self.delay)
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=f"t{i} "))
            if run_manager:
                await run_manager.on_llm_new_token(chunk.text, chunk=chunk)
            yield chunk


async def _no_breaker_call(func, *args, **kwargs):
    return await func(*args, **kwargs)


@pytest.fixture
def breaker():
    b = AsyncMock()
    b.call = _no_breaker_call
    return b


def test_stream_stats_tracks_first_chunk_and_content():
    stats = llm_fallback._StreamStats()
    assert stats.describe() == (
        "first_chunk=- first_content=- chunks=0 content_chunks=0 content_chars=0"
    )
    asyncio.run(stats.on_llm_new_token(""))  # reasoning-only chunk: no content yet
    assert stats.first_chunk_s is not None and stats.first_content_s is None
    asyncio.run(stats.on_llm_new_token("abc"))
    assert stats.first_content_s is not None
    assert stats.chunks == 2 and stats.content_chars == 3
    assert stats.content_chunks == 1, "a reasoning-only chunk must not count as content"


@pytest.mark.asyncio
async def test_stats_handler_does_not_hide_events_from_the_parent_run():
    """Passing callbacks=[stats] outright would replace the inherited manager and
    astream_events would stop seeing model events, which token accounting and the
    debate turn events depend on."""
    llm = _FakeStreamingModel()
    stats = llm_fallback._StreamStats()

    async def node(x):
        return await llm.ainvoke(x, config=llm_fallback._config_with_stats(stats))

    seen: list[str] = []
    async for ev in RunnableLambda(node).astream_events("hi", version="v2"):
        if ev["event"].startswith("on_chat_model"):
            seen.append(ev["event"])

    assert "on_chat_model_end" in seen
    assert stats.chunks >= 6, "stats handler must still receive the streamed tokens"
    assert stats.content_chars > 0


@pytest.mark.asyncio
async def test_timeout_logs_what_had_streamed(breaker, monkeypatch, caplog):
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 0.3)
    llm = _FakeStreamingModel(n_tokens=200, delay=0.02)

    async def node(x):
        with pytest.raises(TimeoutError):
            await llm_fallback._invoke_with_retry(llm, x, breaker=breaker)
        return "done"

    with caplog.at_level("WARNING", logger=llm_fallback.log.name):
        async for _ in RunnableLambda(node).astream_events([], version="v2"):
            pass

    record = next(r for r in caplog.records if "llm_attempt_timeout" in r.getMessage())
    msg = record.getMessage()
    assert "model=fake-model" in msg
    assert "chunks=0" not in msg, "the log must show how much had streamed before cancel"


@pytest.mark.asyncio
async def test_floor_check_tolerates_a_clamped_slice(breaker, monkeypatch):
    """A slice clamped to exactly the floor arrives a few ms short of it; that is
    an attempt to make, not a reason to abort the chain."""
    monkeypatch.setattr(llm_fallback, "_MIN_USEFUL_ATTEMPT_SECONDS", 8.0)
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 45.0)
    llm = _FakeStreamingModel(n_tokens=2, delay=0.01)

    result = await llm_fallback._invoke_with_retry(
        llm, [], breaker=breaker, deadline=time.monotonic() + 7.9
    )
    assert result is not None


@pytest.mark.asyncio
async def test_floor_check_still_rejects_a_truly_exhausted_budget(breaker, monkeypatch):
    monkeypatch.setattr(llm_fallback, "_MIN_USEFUL_ATTEMPT_SECONDS", 8.0)
    llm = _FakeStreamingModel()
    with pytest.raises(TimeoutError, match="budget exhausted"):
        await llm_fallback._invoke_with_retry(
            llm, [], breaker=breaker, deadline=time.monotonic() + 2.0
        )


@pytest.mark.asyncio
async def test_answered_model_names_the_fallback_that_responded():
    async def _retry(llm, messages, *, breaker=None, deadline=None, **_kw):
        if getattr(llm, "_id", "") == "m-primary":
            raise TimeoutError("LLM attempt exceeded 45s wall-clock timeout (model=m-primary)")
        return "ok"

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._id = model
        return m

    llm_fallback.answered_model.set(None)
    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(type(settings), "llm_fallback_chain", property(lambda self: ["m-fallback"])),
    ):
        await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    assert llm_fallback.answered_model.get() == "m-fallback"


def test_chain_reaches_a_different_provider_within_two_fallbacks():
    """One slow Nvidia pool must not be able to take out every early attempt: a
    non-primary-provider model has to appear within the first two fallbacks."""
    primary_provider = settings.llm_model.split("/")[0]
    first_two = settings.llm_fallback_chain[:2]
    assert any(m.split("/")[0] != primary_provider for m in first_two)


def test_reasoning_off_is_only_listed_for_models_that_accept_it():
    """MiniMax rejects reasoning={"enabled": false} (HTTP 400), so it must never be
    listed; every listed model must also be in play (primary or in the chain)."""
    optional = settings.llm_reasoning_optional_set
    assert not any("minimax" in m for m in optional)
    in_play = {settings.llm_model, *settings.llm_fallback_chain}
    assert optional <= in_play


def _recording_build():
    calls: list[tuple[str, bool]] = []

    def _fake(model, temperature, max_tokens, request_timeout, json_mode=True, reasoning_off=False):
        calls.append((model, reasoning_off))
        m = AsyncMock()
        m._id = model
        return m

    return calls, _fake


async def _fail_primary_then_succeed(llm, messages, *, breaker=None, deadline=None, **_kw):
    if llm._id == "m-primary":
        raise TimeoutError("LLM attempt exceeded 45s wall-clock timeout (model=m-primary)")
    return "ok"


@pytest.mark.asyncio
async def test_rescue_attempt_runs_with_reasoning_off_but_primary_keeps_it():
    calls, fake = _recording_build()
    with (
        patch.object(llm_fallback, "_build_llm", side_effect=fake),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_fail_primary_then_succeed),
        patch.object(type(settings), "llm_fallback_chain", property(lambda self: ["m-rescue"])),
        patch.object(
            type(settings),
            "llm_reasoning_optional_set",
            property(lambda self: frozenset({"m-primary", "m-rescue"})),
        ),
    ):
        await llm_fallback.invoke_with_fallback(
            [], primary_model="m-primary", reasoning_off_on_fallback=True
        )

    assert calls == [("m-primary", False), ("m-rescue", True)]


@pytest.mark.asyncio
async def test_reasoning_stays_on_when_the_caller_does_not_ask_for_the_rescue_mode():
    calls, fake = _recording_build()
    with (
        patch.object(llm_fallback, "_build_llm", side_effect=fake),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_fail_primary_then_succeed),
        patch.object(type(settings), "llm_fallback_chain", property(lambda self: ["m-rescue"])),
        patch.object(
            type(settings),
            "llm_reasoning_optional_set",
            property(lambda self: frozenset({"m-primary", "m-rescue"})),
        ),
    ):
        await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    assert calls == [("m-primary", False), ("m-rescue", False)]


@pytest.mark.asyncio
async def test_models_not_allowed_to_disable_reasoning_are_left_alone():
    calls, fake = _recording_build()
    with (
        patch.object(llm_fallback, "_build_llm", side_effect=fake),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_fail_primary_then_succeed),
        patch.object(type(settings), "llm_fallback_chain", property(lambda self: ["m-rescue"])),
        patch.object(
            type(settings), "llm_reasoning_optional_set", property(lambda self: frozenset())
        ),
    ):
        await llm_fallback.invoke_with_fallback(
            [], primary_model="m-primary", reasoning_off_on_fallback=True
        )

    assert calls == [("m-primary", False), ("m-rescue", False)]


def test_build_llm_sends_the_reasoning_switch_only_when_asked(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")  # pragma: allowlist secret
    llm_fallback._build_llm.cache_clear()
    off = llm_fallback._build_llm("m", 0.5, 100, 30, True, True)
    on = llm_fallback._build_llm("m", 0.5, 100, 30, True, False)
    assert off.extra_body == {"reasoning": {"enabled": False}}
    assert not on.extra_body
    llm_fallback._build_llm.cache_clear()


# --- backup-model note on the card ---


def _answer_as(model, reasoning_off=False):
    llm_fallback.answered_model.set(model)
    llm_fallback.answered_reasoning_off.set(reasoning_off)


def test_primary_answering_normally_adds_no_note():
    from src.agent.nodes.debate import _note_turn

    turns: list[dict] = []
    _answer_as(settings.llm_model, reasoning_off=False)
    _note_turn(turns, "bull")
    assert turns == []


def test_backup_model_is_noted():
    from src.agent.nodes.debate import _note_turn

    turns: list[dict] = []
    _answer_as("nvidia/nemotron-3.5-super-vl:free", reasoning_off=True)
    _note_turn(turns, "moderator")
    assert turns == [
        {"turn": "moderator", "model": "nvidia/nemotron-3.5-super-vl:free", "reasoning_off": True}
    ]


def test_primary_with_reasoning_off_is_still_noted():
    from src.agent.nodes.debate import _note_turn

    turns: list[dict] = []
    _answer_as(settings.llm_model, reasoning_off=True)
    _note_turn(turns, "bear")
    assert turns[0]["reasoning_off"] is True


def test_nothing_recorded_when_no_model_answered():
    from src.agent.nodes.debate import _note_turn

    turns: list[dict] = []
    llm_fallback.answered_model.set(None)
    _note_turn(turns, "bull")
    assert turns == []


@pytest.mark.asyncio
async def test_reasoning_off_flag_is_recorded_for_the_answering_attempt():
    async def _retry(llm, messages, *, breaker=None, deadline=None, **_kw):
        if llm._id == "m-primary":
            raise TimeoutError("LLM attempt exceeded 45s wall-clock timeout (model=m-primary)")
        return "ok"

    def _fake_build(model, *_a, **_k):
        m = AsyncMock()
        m._id = model
        return m

    _answer_as(None, False)
    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(type(settings), "llm_fallback_chain", property(lambda self: ["m-rescue"])),
        patch.object(
            type(settings),
            "llm_reasoning_optional_set",
            property(lambda self: frozenset({"m-rescue"})),
        ),
    ):
        await llm_fallback.invoke_with_fallback(
            [], primary_model="m-primary", reasoning_off_on_fallback=True
        )

    assert llm_fallback.answered_model.get() == "m-rescue"
    assert llm_fallback.answered_reasoning_off.get() is True


# --- dead-route (404) detection ---


class _HttpError(Exception):
    def __init__(self, status_code, message="boom"):
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.parametrize(
    "exc",
    [
        _HttpError(404, "Not found"),
        Exception(
            "Error code: 404 - {'error': {'message': 'Provider returned error', 'code': 404}}"
        ),
        Exception("Error code: 404 - This model is unavailable for free."),
    ],
)
def test_real_404s_walk_the_chain(exc):
    assert llm_fallback._classify_error(exc) is llm_fallback.ErrorSeverity.FALLBACK_TO_OTHER


@pytest.mark.parametrize(
    "message",
    [
        "Upstream error id req-4040-abc",
        "Internal server error: processed 404 tokens before failing",
        "Service unavailable. See https://status.example.com/incidents/404",
    ],
)
def test_a_404_that_is_only_a_substring_is_not_a_dead_route(message):
    # Some other branch may still route these to a fallback; what matters here is
    # that the 404 check itself does not claim them.
    assert not llm_fallback._is_dead_model_route(Exception(message), message.lower())


def test_structured_status_beats_message_text():
    # A 500 whose text happens to contain "404" must not be read as a dead route.
    exc = _HttpError(500, "Error code: 404 echoed from upstream body")
    assert llm_fallback._is_dead_model_route(exc, str(exc).lower()) is False


def test_429_with_404_in_the_body_still_follows_the_429_path():
    exc = Exception("Error code: 429 - rate limited, request 404 retried")
    assert llm_fallback._classify_error(exc) is llm_fallback.ErrorSeverity.RETRY_SAME_MODEL


# --- stalled backup attempts ---


class _SilentModel:
    """Accepts the call and then produces nothing, like a stalled upstream."""

    model = "silent-model"

    async def ainvoke(self, _messages, config=None):
        await asyncio.sleep(30)


class _SlowFirstOutputModel(BaseChatModel):
    """Emits its first token after a delay, then finishes."""

    model: str = "slow-start"
    first_delay: float = 0.15

    @property
    def _llm_type(self) -> str:
        return "slow-start"

    def _generate(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    async def _agenerate(self, messages, stop=None, run_manager=None, **kw):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="full"))])

    async def _astream(self, messages, stop=None, run_manager=None, **kw):
        await asyncio.sleep(self.first_delay)
        for i in range(3):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=f"t{i} "))
            if run_manager:
                await run_manager.on_llm_new_token(chunk.text, chunk=chunk)
            yield chunk


@pytest.mark.asyncio
async def test_backup_attempt_with_no_output_is_abandoned_early(breaker, monkeypatch):
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 20.0)
    start = time.monotonic()
    with pytest.raises(TimeoutError, match="no output"):
        await llm_fallback._invoke_with_retry(
            _SilentModel(), [], breaker=breaker, first_output_deadline=0.3
        )
    assert time.monotonic() - start < 3.0, "must not wait out the whole attempt"


@pytest.mark.asyncio
async def test_stalled_attempt_is_classified_so_the_chain_moves_on(breaker):
    with pytest.raises(TimeoutError) as info:
        await llm_fallback._invoke_with_retry(
            _SilentModel(), [], breaker=breaker, first_output_deadline=0.2
        )
    assert llm_fallback._is_fallback_worthy(info.value)


@pytest.mark.asyncio
async def test_backup_that_starts_in_time_is_not_cut_off(breaker, monkeypatch):
    monkeypatch.setattr(settings, "llm_attempt_timeout_seconds", 20.0)
    llm = _SlowFirstOutputModel(first_delay=0.1)
    holder: dict = {}

    async def node(x):
        holder["result"] = await llm_fallback._invoke_with_retry(
            llm, x, breaker=breaker, first_output_deadline=1.0
        )
        return "done"

    async for _ in RunnableLambda(node).astream_events([], version="v2"):
        pass

    assert holder.get("result") is not None


@pytest.mark.asyncio
async def test_primary_never_gets_the_early_stall_deadline():
    seen: list[float | None] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None, first_output_deadline=None):
        seen.append(first_output_deadline)
        if len(seen) == 1:
            raise TimeoutError("LLM attempt exceeded 45s wall-clock timeout (model=m-primary)")
        return "ok"

    def _fake_build(model, *_a, **_k):
        return AsyncMock()

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=_fake_build),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(type(settings), "llm_fallback_chain", property(lambda self: ["m-backup"])),
    ):
        await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    assert seen[0] is None, "the primary keeps its full reasoning window"
    assert seen[1] == settings.llm_backup_first_output_seconds


@pytest.mark.asyncio
async def test_stall_deadline_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "llm_backup_first_output_seconds", 0)
    seen: list[float | None] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None, first_output_deadline=None):
        seen.append(first_output_deadline)
        if len(seen) == 1:
            raise TimeoutError("LLM attempt exceeded 45s wall-clock timeout (model=m-primary)")
        return "ok"

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=lambda *a, **k: AsyncMock()),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(type(settings), "llm_fallback_chain", property(lambda self: ["m-backup"])),
    ):
        await llm_fallback.invoke_with_fallback([], primary_model="m-primary")

    assert seen == [None, None]


# --- reservation that could never be used ---


@pytest.mark.asyncio
async def test_a_reserve_smaller_than_the_floor_is_not_held_back(monkeypatch):
    """12s left, two models: holding 6s for a model that needs 8s to start only
    shrinks the first backup's slice. The whole 12s should go to it."""
    monkeypatch.setattr(llm_fallback, "_MIN_USEFUL_ATTEMPT_SECONDS", 8.0)
    budgets: list[float] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None, **_kw):
        budgets.append(round(deadline - time.monotonic(), 1))
        return "ok"

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=lambda *a, **k: AsyncMock()),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(type(settings), "llm_fallback_chain", property(lambda self: ["m-backup"])),
    ):
        await llm_fallback.invoke_with_fallback(
            [], primary_model="m-primary", deadline=time.monotonic() + 12.0
        )

    assert budgets[0] >= 11.5, f"primary should keep the full 12s, got {budgets[0]}"


@pytest.mark.asyncio
async def test_a_real_reserve_is_still_held_back_when_there_is_room(monkeypatch):
    monkeypatch.setattr(llm_fallback, "_MIN_USEFUL_ATTEMPT_SECONDS", 8.0)
    budgets: list[float] = []

    async def _retry(llm, messages, *, breaker=None, deadline=None, **_kw):
        budgets.append(round(deadline - time.monotonic(), 1))
        raise TimeoutError("LLM attempt exceeded 45s wall-clock timeout (model=x)")

    with (
        patch.object(llm_fallback, "_build_llm", side_effect=lambda *a, **k: AsyncMock()),
        patch.object(llm_fallback, "_invoke_with_retry", side_effect=_retry),
        patch.object(type(settings), "llm_fallback_chain", property(lambda self: ["m-backup"])),
    ):
        with pytest.raises(TimeoutError):
            await llm_fallback.invoke_with_fallback(
                [], primary_model="m-primary", deadline=time.monotonic() + 60.0
            )

    # 60s left: 12s is held back, so the primary is capped near 48s.
    assert 47.0 <= budgets[0] <= 48.5


# --- finish reason normalisation ---


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("stop", "stop"),
        ("stopstop", "stop"),
        ("lengthlength", "length"),
        ("length", "length"),
        ("tool_callstool_calls", "tool_calls"),
        (None, None),
        ("", None),
        ("something_else", "something_else"),
    ],
)
def test_finish_reason_is_collapsed_to_the_plain_value(raw, expected):
    assert llm_fallback._normalize_finish_reason(raw) == expected
