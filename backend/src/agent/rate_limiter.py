"""
Global LLM rate limiter. Process-wide token bucket for OpenRouter free tier (20 req/min).

All LLM calls should acquire a slot before invoking the provider to prevent
cascading 429s across concurrent analyses, chats, and scheduled jobs.
"""

import asyncio
import time


class TokenBucket:
    """Simple async token bucket rate limiter."""

    def __init__(self, rate: float, capacity: int):
        """
        Args:
            rate: tokens added per second
            capacity: max tokens in bucket
        """
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float = 30.0) -> bool:
        """Wait for a token. Returns True if acquired, False on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            async with self._lock:
                now = time.monotonic()
                self._refill(now)

                # Strict timeout: never grant a token after the deadline
                if now >= deadline:
                    return False

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True

                # Compute adaptive sleep: time until next token becomes available
                wait_for_token = (1.0 - self._tokens) / self._rate

            # Sleep for the shorter of time-to-next-token or remaining timeout
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(wait_for_token, remaining))

    def _refill(self, now: float | None = None):
        if now is None:
            now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now


# OpenRouter free tier: 20 req/min = 0.333 req/sec
# With 2 Fly.io machines, each instance gets half the budget to prevent
# aggregate rate from exceeding the provider limit.
# 10/min per instance (0.167/sec) with burst capacity of 5.
llm_limiter = TokenBucket(rate=10.0 / 60.0, capacity=5)


class RateLimitExceeded(Exception):
    """Raised when the rate limiter cannot acquire a slot within timeout."""

    def __init__(self, timeout: float):
        super().__init__(f"Rate limit: could not acquire slot within {timeout}s")
        self.timeout = timeout


async def acquire_or_raise(timeout: float = 30.0) -> None:
    """Acquire a rate limiter slot or raise RateLimitExceeded."""
    if not await llm_limiter.acquire(timeout=timeout):
        raise RateLimitExceeded(timeout)
