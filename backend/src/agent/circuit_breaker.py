"""
Circuit breaker for LLM API calls.

States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (probing)

Sliding window: if failure_threshold failures occur within window_seconds,
the circuit opens. After recovery_seconds, it moves to half-open and allows
one probe request through. Only a successful probe closes the circuit.
"""

import asyncio
import re
import time
from collections import deque
from enum import Enum
from typing import Any, Callable, TypeVar

from src.logging_config import get_logger

log = get_logger("circuit_breaker")

T = TypeVar("T")


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Return True if the exception represents a rate-limit (429) response.

    Rate-limit errors mean the provider is healthy but throttling us.
    They should NOT count as circuit breaker failures to avoid death spirals.
    """
    exc_str = str(exc).lower()
    if re.search(r"\b429\b", exc_str):
        return True
    if "rate limit" in exc_str or "rate_limit" in exc_str:
        return True
    return False


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
        adaptation_alpha: float = 0.3,
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

        # Adaptive rate-limit tracking
        self._base_recovery_seconds: float = recovery_seconds
        self._adaptation_alpha: float = adaptation_alpha
        self._rate_limit_ewma: float = 0.0
        self._adaptation_factor: float = 1.0
        self._total_calls: int = 0
        self._rate_limit_calls: int = 0

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
        except Exception as exc:
            # Rate-limit errors (429) should NOT trip the circuit breaker.
            # They indicate the provider is healthy but throttling us, which
            # is expected behavior under load. Counting them as failures
            # creates a death spiral: 429s open breaker -> 30s outage ->
            # recovery -> immediate 429s -> reopen.
            if _is_rate_limit_error(exc):
                log.info("circuit_rate_limit_ignored", breaker=self.name)
                self._track_rate_limit(exc)
                if is_probe:
                    # Rate limit during probe: backend is reachable, close circuit
                    await self._on_success(is_probe)
                raise
            await self._on_failure(is_probe)
            raise
        else:
            await self._on_success(is_probe)
            return result

    async def _on_success(self, is_probe: bool) -> None:
        self._track_success()
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

    def _track_rate_limit(self, exc: BaseException) -> None:
        """Update EWMA of rate-limit frequency and adapt thresholds."""
        self._total_calls += 1
        self._rate_limit_calls += 1
        # EWMA: blend new observation (1.0 = rate limited) with history
        self._rate_limit_ewma = (
            self._adaptation_alpha * 1.0
            + (1 - self._adaptation_alpha) * self._rate_limit_ewma
        )
        self._compute_adaptation()

    def _track_success(self) -> None:
        """Record a successful (non-429) call for EWMA."""
        self._total_calls += 1
        self._rate_limit_ewma = (
            self._adaptation_alpha * 0.0
            + (1 - self._adaptation_alpha) * self._rate_limit_ewma
        )
        self._compute_adaptation()

    def _compute_adaptation(self) -> None:
        """Adjust recovery_seconds based on rate-limit pressure."""
        if self._rate_limit_ewma > 0.3:
            # High pressure: scale up to 3x
            self._adaptation_factor = min(
                3.0, 1.0 + (self._rate_limit_ewma - 0.3) * (2.0 / 0.7)
            )
        elif self._rate_limit_ewma < 0.1:
            # Low pressure: relax toward 1.0
            self._adaptation_factor = max(1.0, self._adaptation_factor * 0.95)
        # Apply
        self.recovery_seconds = self._base_recovery_seconds * self._adaptation_factor

    @property
    def adaptation_state(self) -> dict[str, Any]:
        """Return adaptive circuit breaker metrics for the ops dashboard."""
        return {
            "rate_limit_ewma": round(self._rate_limit_ewma, 4),
            "adaptation_factor": round(self._adaptation_factor, 4),
            "effective_recovery": round(self.recovery_seconds, 2),
            "total_calls": self._total_calls,
            "rate_limit_calls": self._rate_limit_calls,
        }


# Singleton for the LLM provider
llm_breaker = CircuitBreaker(
    name="llm_api",
    failure_threshold=5,
    window_seconds=60.0,
    recovery_seconds=30.0,
)
