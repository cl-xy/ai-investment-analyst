"""Tests for the circuit breaker module."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
)


@pytest.fixture(autouse=True)
def _bypass_rate_limiter():
    """Bypass the global LLM rate limiter so tests don't starve for tokens."""
    mock_acquire = AsyncMock(return_value=True)
    with patch("src.agent.rate_limiter.llm_limiter.acquire", mock_acquire):
        yield


@pytest.fixture
def breaker():
    """Create a circuit breaker with low thresholds for fast tests."""
    return CircuitBreaker(
        name="test",
        failure_threshold=3,
        window_seconds=10.0,
        recovery_seconds=0.1,
    )


class TestCircuitBreakerTransitions:
    @pytest.mark.asyncio
    async def test_starts_closed(self, breaker):
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_closed_to_open_after_threshold_failures(self, breaker):
        async def failing():
            raise RuntimeError("boom")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call(failing)

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_rejects_calls_with_retry_after(self, breaker):
        async def failing():
            raise RuntimeError("boom")

        # Trip the breaker
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call(failing)

        # Next call should raise CircuitBreakerOpen
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await breaker.call(failing)

        assert exc_info.value.retry_after >= 0

    @pytest.mark.asyncio
    async def test_open_to_half_open_after_recovery(self, breaker):
        async def failing():
            raise RuntimeError("boom")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call(failing)

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery
        await asyncio.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_to_closed_on_success(self, breaker):
        async def failing():
            raise RuntimeError("boom")

        async def succeeding():
            return "ok"

        # Trip breaker
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call(failing)

        # Wait for half-open
        await asyncio.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # Success should close it
        result = await breaker.call(succeeding)
        assert result == "ok"
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failures_outside_window_dont_trip(self):
        breaker = CircuitBreaker(
            name="windowed",
            failure_threshold=3,
            window_seconds=0.05,
            recovery_seconds=1.0,
        )

        async def failing():
            raise RuntimeError("boom")

        # Two failures
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await breaker.call(failing)

        # Wait for window to expire
        await asyncio.sleep(0.1)

        # One more failure (previous two should be outside window now)
        with pytest.raises(RuntimeError):
            await breaker.call(failing)

        # Should still be closed (only 1 failure in window)
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_success_does_not_clear_sliding_window(self, breaker):
        """Successes do not reset failure history; failures age out by timestamp."""
        call_count = 0

        async def sometimes_fails():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("transient")
            return "ok"

        # Two failures
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await breaker.call(sometimes_fails)

        # One success does NOT clear the failure window
        result = await breaker.call(sometimes_fails)
        assert result == "ok"
        assert breaker.state == CircuitState.CLOSED

        # One more failure tips us to threshold (2 prior + 1 new = 3 >= threshold)
        async def failing():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await breaker.call(failing)

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_aged_out_failures_dont_count(self):
        """Failures outside the sliding window don't count toward threshold."""
        breaker = CircuitBreaker(
            name="aging",
            failure_threshold=3,
            window_seconds=0.05,
            recovery_seconds=1.0,
        )

        async def failing():
            raise RuntimeError("boom")

        async def succeeding():
            return "ok"

        # Two failures
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await breaker.call(failing)

        # Wait for them to age out of the window
        await asyncio.sleep(0.1)

        # A success trims the aged-out failures
        result = await breaker.call(succeeding)
        assert result == "ok"

        # Two more failures (only these are in the window now: 2 < threshold)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await breaker.call(failing)

        assert breaker.state == CircuitState.CLOSED
