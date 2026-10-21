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
    assert stats.describe() == "first_chunk=- first_content=- chunks=0 content_chars=0"
    asyncio.run(stats.on_llm_new_token(""))  # reasoning-only chunk: no content yet
    assert stats.first_chunk_s is not None and stats.first_content_s is None
    asyncio.run(stats.on_llm_new_token("abc"))
    assert stats.first_content_s is not None
    assert stats.chunks == 2 and stats.content_chars == 3


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
    async def _retry(llm, messages, *, breaker=None, deadline=None):
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


def test_second_model_in_the_chain_is_not_from_the_primarys_provider():
    """One slow Nvidia pool must not be able to take out both the primary and the
    first fallback."""
    primary_provider = settings.llm_model.split("/")[0]
    first_fallback = settings.llm_fallback_chain[0]
    assert first_fallback.split("/")[0] != primary_provider
