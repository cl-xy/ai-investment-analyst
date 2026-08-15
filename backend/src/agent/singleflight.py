"""
Request coalescing (singleflight) for concurrent duplicate ticker analyses.

When multiple requests arrive for the same ticker within a short window,
only one LLM pipeline executes. Others await the same result.
Prevents wasted rate-limit budget on duplicate work.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from src.logging_config import get_logger

log = get_logger("singleflight")

# How long a completed result stays cached for coalescing (seconds)
_RESULT_TTL = 30.0

# How long to wait for an in-flight request before giving up (seconds)
_WAIT_TIMEOUT = 200.0


@dataclass
class _Flight:
    """A single in-flight or recently-completed analysis."""

    future: asyncio.Future
    created_at: float = field(default_factory=time.monotonic)
    completed_at: float | None = None


class Singleflight:
    """Coalesce concurrent requests for the same key (ticker).

    First caller runs the actual work. Subsequent callers for the same key
    await the same future. Results are cached briefly to coalesce near-misses.
    """

    def __init__(self, result_ttl: float = _RESULT_TTL):
        self._flights: dict[str, _Flight] = {}
        self._lock = asyncio.Lock()
        self._result_ttl = result_ttl

    async def do(self, key: str, func, *args, **kwargs) -> Any:
        """Execute func or join an existing in-flight call for the same key.

        Returns the result (shared across all waiters for the same key).
        Raises whatever exception the original caller encountered.
        """
        async with self._lock:
            self._evict_expired()

            if key in self._flights:
                flight = self._flights[key]
                if not flight.future.done():
                    log.info("singleflight_join", key=key)
                    # Join existing in-flight request
                elif (
                    flight.completed_at
                    and (time.monotonic() - flight.completed_at) < self._result_ttl
                ):
                    log.info("singleflight_cached", key=key)
                    # Return cached result
                    return flight.future.result()
                else:
                    # Expired, start new flight
                    del self._flights[key]

            if key not in self._flights:
                # First caller: create the flight
                loop = asyncio.get_event_loop()
                future = loop.create_future()
                self._flights[key] = _Flight(future=future)
                is_owner = True
            else:
                is_owner = False

        if is_owner:
            try:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=_WAIT_TIMEOUT)
                async with self._lock:
                    if key in self._flights:
                        self._flights[key].future.set_result(result)
                        self._flights[key].completed_at = time.monotonic()
                return result
            except BaseException as exc:
                async with self._lock:
                    if key in self._flights:
                        flight = self._flights[key]
                        if not flight.future.done():
                            flight.future.set_exception(exc)
                        del self._flights[key]
                raise
        else:
            # Wait for the owner to complete
            flight = self._flights[key]
            try:
                return await asyncio.wait_for(asyncio.shield(flight.future), timeout=_WAIT_TIMEOUT)
            except asyncio.TimeoutError:
                log.warning("singleflight_timeout", key=key)
                raise

    def _evict_expired(self) -> None:
        """Remove completed flights past their TTL. Must hold _lock."""
        now = time.monotonic()
        expired = [
            k
            for k, f in self._flights.items()
            if f.completed_at and (now - f.completed_at) > self._result_ttl
        ]
        for k in expired:
            del self._flights[k]

    @property
    def in_flight(self) -> dict[str, float]:
        """Return currently in-flight keys with their age in seconds."""
        now = time.monotonic()
        return {k: now - f.created_at for k, f in self._flights.items() if not f.future.done()}

    @property
    def stats(self) -> dict[str, int]:
        """Return coalescing statistics for the ops dashboard."""
        total = len(self._flights)
        active = sum(1 for f in self._flights.values() if not f.future.done())
        cached = sum(1 for f in self._flights.values() if f.future.done() and f.completed_at)
        return {"active": active, "cached": cached, "total": total}


# Module-level singleton
analysis_singleflight = Singleflight()
