"""
Circuit breaker for LLM API calls.

States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (probing)

Sliding window: if failure_threshold failures occur within window_seconds,
the circuit opens. After recovery_seconds, it moves to half-open and allows
one probe request through.
"""

import asyncio
import time
from collections import deque
from enum import Enum
from typing import Any, Callable, TypeVar

from src.logging_config import get_logger

log = get_logger("circuit_breaker")

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when circuit is open and calls are rejected."""

    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker open, retry after {retry_after:.1f}s")


class CircuitBreaker:
    """Sliding-window circuit breaker for async callables."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        recovery_seconds: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.recovery_seconds = recovery_seconds

        self._state = CircuitState.CLOSED
        self._failures: deque[float] = deque()
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_seconds:
                return CircuitState.HALF_OPEN
        return self._state

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute func through the circuit breaker with rate limiting."""
        from .rate_limiter import groq_limiter

        # Acquire lock to atomically read state and claim probe slot if HALF_OPEN.
        # This prevents the thundering-herd problem where multiple coroutines all
        # see HALF_OPEN and proceed to make concurrent probe calls.
        async with self._lock:
            state = self.state
            if state == CircuitState.OPEN:
                retry_after = self.recovery_seconds - (
                    time.monotonic() - self._last_failure_time
                )
                raise CircuitBreakerOpen(retry_after=max(0, retry_after))

            if state == CircuitState.HALF_OPEN:
                # Claim the probe slot: transition to CLOSED optimistically.
                # - First coroutine sees HALF_OPEN, sets CLOSED, proceeds to probe.
                # - Subsequent coroutines see CLOSED and proceed normally.
                # - If the probe fails, _on_failure will re-open the circuit.
                # - If it succeeds, _on_success confirms CLOSED (no-op).
                self._state = CircuitState.CLOSED
                log.info("circuit_half_open_probe", breaker=self.name)

        # Acquire rate limiter slot before calling
        acquired = await groq_limiter.acquire(timeout=30.0)
        if not acquired:
            # Rate limiter exhaustion is a throttling signal, not an API failure.
            # Don't count it toward circuit breaker failures — just reject this call.
            raise CircuitBreakerOpen(retry_after=5.0)

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except CircuitBreakerOpen:
            raise
        except Exception as exc:
            await self._on_failure()
            raise exc

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                log.info("circuit_closed", breaker=self.name)
            self._state = CircuitState.CLOSED
            self._failures.clear()

    async def _on_failure(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._failures.append(now)
            self._last_failure_time = now

            # Trim failures outside the window
            cutoff = now - self.window_seconds
            while self._failures and self._failures[0] < cutoff:
                self._failures.popleft()

            if len(self._failures) >= self.failure_threshold:
                self._state = CircuitState.OPEN
                log.warning(
                    "circuit_opened",
                    breaker=self.name,
                    failures=len(self._failures),
                    window=self.window_seconds,
                )


# Singleton for the LLM provider
groq_breaker = CircuitBreaker(
    name="groq_api",
    failure_threshold=5,
    window_seconds=60.0,
    recovery_seconds=30.0,
)
