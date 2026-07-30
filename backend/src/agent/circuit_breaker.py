"""
Circuit breaker for LLM API calls.

States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (probing)

Sliding window: if failure_threshold failures occur within window_seconds,
the circuit opens. After recovery_seconds, it moves to half-open and allows
one probe request through. Only a successful probe closes the circuit.
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


class CircuitBreakerRateLimited(CircuitBreakerOpen):
    """Raised when the rate limiter rejects a call (circuit may be healthy).

    Subclasses CircuitBreakerOpen for backward compatibility with existing
    callers that catch CircuitBreakerOpen broadly.
    """

    pass


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
        self._probe_in_flight: bool = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Computed state view (read-only, does not mutate internal state)."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_seconds:
                return CircuitState.HALF_OPEN
        return self._state

    def _refresh_state_locked(self) -> CircuitState:
        """Transition OPEN -> HALF_OPEN if recovery time elapsed. Must hold _lock."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_seconds:
                self._state = CircuitState.HALF_OPEN
                self._probe_in_flight = False
        return self._state

    def _trim_window(self, now: float) -> None:
        """Remove failure timestamps outside the sliding window. Must hold _lock."""
        cutoff = now - self.window_seconds
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute func through the circuit breaker with rate limiting."""
        from .rate_limiter import llm_limiter

        is_probe = False

        # Acquire lock to atomically read state and claim probe slot if HALF_OPEN.
        # Only one coroutine can claim the probe; others are rejected immediately.
        async with self._lock:
            state = self._refresh_state_locked()

            if state == CircuitState.OPEN:
                retry_after = self.recovery_seconds - (
                    time.monotonic() - self._last_failure_time
                )
                raise CircuitBreakerOpen(retry_after=max(0, retry_after))

            if state == CircuitState.HALF_OPEN:
                if self._probe_in_flight:
                    # Another coroutine is already probing; reject this one.
                    raise CircuitBreakerOpen(retry_after=5.0)
                # Claim the exclusive probe slot.
                self._probe_in_flight = True
                is_probe = True
                log.info("circuit_half_open_probe", breaker=self.name)

        # Acquire rate limiter slot before calling
        acquired = await llm_limiter.acquire(timeout=30.0)
        if not acquired:
            # Rate limiter exhaustion: revert probe slot if this was a probe.
            if is_probe:
                async with self._lock:
                    self._probe_in_flight = False
                    # Stay HALF_OPEN so next caller can attempt the probe.
            raise CircuitBreakerRateLimited(retry_after=5.0)

        try:
            result = await func(*args, **kwargs)
        except asyncio.CancelledError:
            # Cancellation is not a backend failure, but clean up probe state.
            if is_probe:
                async with self._lock:
                    self._state = CircuitState.OPEN
                    self._probe_in_flight = False
            raise
        except CircuitBreakerOpen:
            raise
        except Exception:
            await self._on_failure(is_probe)
            raise
        else:
            await self._on_success(is_probe)
            return result

    async def _on_success(self, is_probe: bool) -> None:
        async with self._lock:
            if is_probe:
                # Successful probe: circuit is confirmed healthy.
                log.info("circuit_closed", breaker=self.name)
                self._state = CircuitState.CLOSED
                self._probe_in_flight = False
                self._failures.clear()
            else:
                # Normal success in CLOSED state: only age out expired failures.
                # Do not clear the sliding window; let failures expire naturally.
                self._trim_window(time.monotonic())

    async def _on_failure(self, is_probe: bool) -> None:
        async with self._lock:
            now = time.monotonic()

            if is_probe:
                # Failed probe: immediately re-open the circuit regardless of
                # the sliding window count. The backend is still unhealthy.
                self._state = CircuitState.OPEN
                self._probe_in_flight = False
                self._last_failure_time = now
                log.warning(
                    "circuit_probe_failed",
                    breaker=self.name,
                )
                return

            # Normal failure in CLOSED state: sliding window logic.
            self._failures.append(now)
            self._last_failure_time = now
            self._trim_window(now)

            if len(self._failures) >= self.failure_threshold:
                self._state = CircuitState.OPEN
                log.warning(
                    "circuit_opened",
                    breaker=self.name,
                    failures=len(self._failures),
                    window=self.window_seconds,
                )


# Singleton for the LLM provider
llm_breaker = CircuitBreaker(
    name="llm_api",
    failure_threshold=5,
    window_seconds=60.0,
    recovery_seconds=30.0,
)
