"""Tests for LLM error classification and the retry/fallback chain."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agent.circuit_breaker import CircuitBreakerOpen
from src.agent.llm_fallback import (
    ErrorSeverity,
    _classify_error,
    _is_fallback_worthy,
    _is_retryable_error,
    invoke_with_fallback,
)


class TestClassifyError:
    """_classify_error decides whether an LLM error is retried, falls back, or is fatal."""

    @pytest.mark.parametrize(
        "message",
        [
            "The server is temporarily unavailable",
            "temporary failure in name resolution",
            "temporarily rate limited, please slow down",
        ],
    )
    def test_temporary_variants_are_retryable(self, message):
        """Regression: 'temporarily' must match, not just the exact word 'temporary'."""
        assert _classify_error(RuntimeError(message)) == ErrorSeverity.RETRY_SAME_MODEL

    @pytest.mark.parametrize(
        "message",
        [
            "Service overloaded",
            "model is overloaded, please retry",
            "Upstream error from Nvidia: overloaded_error",
            "Service temporarily overloaded",
            "Upstream error from Nvidia: Service temporarily overloaded",
        ],
    )
    def test_overloaded_falls_back_to_other_model(self, message):
        """Sustained overload should route to the fallback model, not just retry the same one."""
        assert _classify_error(RuntimeError(message)) == ErrorSeverity.FALLBACK_TO_OTHER

    def test_circuit_breaker_open_falls_back(self):
        assert (
            _classify_error(CircuitBreakerOpen(retry_after=1.0))
            == ErrorSeverity.FALLBACK_TO_OTHER
        )

    @pytest.mark.parametrize(
        "message",
        [
            "429 Too Many Requests",
            "rate limit exceeded",
            "connection reset by peer",
            "service unavailable",
        ],
    )
    def test_retryable_patterns(self, message):
        assert _classify_error(RuntimeError(message)) == ErrorSeverity.RETRY_SAME_MODEL

    @pytest.mark.parametrize(
        "message",
        [
            "resource exhausted: quota exceeded",
            "502 Bad Gateway",
            "503 Service Unavailable",
            "request timeout after 120s",
        ],
    )
    def test_fallback_patterns(self, message):
        assert _classify_error(RuntimeError(message)) == ErrorSeverity.FALLBACK_TO_OTHER

    @pytest.mark.parametrize(
        "message",
        [
            "401 Unauthorized",
            "400 Bad Request",
            "invalid api key: unauthorized",
        ],
    )
    def test_auth_errors_not_retryable(self, message):
        assert _classify_error(RuntimeError(message)) == ErrorSeverity.NOT_RETRYABLE

    def test_unknown_error_not_retryable(self):
        assert _classify_error(RuntimeError("something completely unexpected")) == (
            ErrorSeverity.NOT_RETRYABLE
        )


class TestRetryAndFallbackHelpers:
    def test_is_retryable_error_true_only_for_retry_same_model(self):
        assert _is_retryable_error(RuntimeError("temporarily unavailable")) is True
        assert _is_retryable_error(RuntimeError("502 Bad Gateway")) is False
        assert _is_retryable_error(RuntimeError("401 Unauthorized")) is False

    def test_is_fallback_worthy_false_only_for_not_retryable(self):
        assert _is_fallback_worthy(RuntimeError("temporarily overloaded")) is True
        assert _is_fallback_worthy(RuntimeError("502 Bad Gateway")) is True
        assert _is_fallback_worthy(RuntimeError("401 Unauthorized")) is False


async def _passthrough_call(fn, *args, **kwargs):
    """Bypass real circuit breaker bookkeeping; just invoke the wrapped call."""
    return await fn(*args, **kwargs)


@pytest.fixture(autouse=True)
def _bypass_breakers():
    with (
        patch("src.agent.llm_fallback.llm_breaker.call", new=AsyncMock(side_effect=_passthrough_call)),
        patch(
            "src.agent.llm_fallback._fallback_breaker.call",
            new=AsyncMock(side_effect=_passthrough_call),
        ),
    ):
        yield


class TestInvokeWithFallback:
    """End-to-end behavior of invoke_with_fallback given classified errors."""

    @pytest.mark.asyncio
    async def test_overloaded_primary_falls_back_to_secondary(self):
        primary_llm = AsyncMock()
        primary_llm.ainvoke.side_effect = RuntimeError(
            "Upstream error from Nvidia: Service temporarily overloaded"
        )
        fallback_llm = AsyncMock()
        fallback_llm.ainvoke.return_value = "fallback-response"

        with patch("src.agent.llm_fallback._build_llm") as mock_build:
            mock_build.side_effect = [primary_llm, fallback_llm]
            result = await invoke_with_fallback(
                messages=[],
                primary_model="nvidia/primary",
                fallback_model="nvidia/fallback",
            )

        assert result == "fallback-response"
        fallback_llm.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_retryable_error_skips_fallback(self):
        primary_llm = AsyncMock()
        primary_llm.ainvoke.side_effect = RuntimeError("401 Unauthorized")
        fallback_llm = AsyncMock()

        with patch("src.agent.llm_fallback._build_llm") as mock_build:
            mock_build.side_effect = [primary_llm, fallback_llm]
            with pytest.raises(RuntimeError, match="401 Unauthorized"):
                await invoke_with_fallback(
                    messages=[],
                    primary_model="nvidia/primary",
                    fallback_model="nvidia/fallback",
                )

        fallback_llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_transient_error_retries_same_model_before_success(self):
        primary_llm = AsyncMock()
        primary_llm.ainvoke.side_effect = [
            RuntimeError("temporarily overloaded"),
            "primary-response",
        ]

        with patch("src.agent.llm_fallback._build_llm") as mock_build:
            mock_build.return_value = primary_llm
            result = await invoke_with_fallback(
                messages=[],
                primary_model="nvidia/primary",
                fallback_model="nvidia/fallback",
            )

        assert result == "primary-response"
        assert primary_llm.ainvoke.await_count == 2

    @pytest.mark.asyncio
    async def test_both_models_failing_raises_fallback_exception(self):
        primary_llm = AsyncMock()
        primary_llm.ainvoke.side_effect = RuntimeError("503 Service Unavailable")
        fallback_llm = AsyncMock()
        fallback_llm.ainvoke.side_effect = RuntimeError("fallback also down")

        with patch("src.agent.llm_fallback._build_llm") as mock_build:
            mock_build.side_effect = [primary_llm, fallback_llm]
            with pytest.raises(RuntimeError, match="fallback also down"):
                await invoke_with_fallback(
                    messages=[],
                    primary_model="nvidia/primary",
                    fallback_model="nvidia/fallback",
                )
