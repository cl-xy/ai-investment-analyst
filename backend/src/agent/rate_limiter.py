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
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True

            # Wait before retrying
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(0.5, remaining))

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now


# OpenRouter free tier: 20 req/min = 0.333 req/sec
# Use 18/min (0.3/sec) with burst capacity of 10 to handle multi-ticker analyses
llm_limiter = TokenBucket(rate=18.0 / 60.0, capacity=10)

# Keep backward-compat alias
groq_limiter = llm_limiter


class RateLimitExceeded(Exception):
    """Raised when the rate limiter cannot acquire a slot within timeout."""

    def __init__(self, timeout: float):
        super().__init__(f"Rate limit: could not acquire slot within {timeout}s")
        self.timeout = timeout


async def acquire_or_raise(timeout: float = 30.0) -> None:
    """Acquire a rate limiter slot or raise RateLimitExceeded."""
    if not await llm_limiter.acquire(timeout=timeout):
        raise RateLimitExceeded(timeout)
