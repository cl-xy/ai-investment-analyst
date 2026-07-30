"""Global concurrency limits for analysis runs.

Per-process semaphore limiting concurrent analysis pipelines. Note: this is
per-process only; multiple Fly.io machines each maintain independent limits.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.logging_config import get_logger

log = get_logger("concurrency")

# Max concurrent full analysis pipelines per instance
MAX_CONCURRENT_ANALYSES = 3
_ACQUIRE_TIMEOUT = 5.0

_analysis_semaphore = asyncio.BoundedSemaphore(MAX_CONCURRENT_ANALYSES)
_slots_in_use = 0


@asynccontextmanager
async def analysis_slot(timeout: float = _ACQUIRE_TIMEOUT) -> AsyncIterator[bool]:
    """Cancellation-safe context manager for analysis slot acquisition.

    Yields True if a slot was acquired, False on timeout. Guarantees release
    on exit (including task cancellation from SSE client disconnects).

    Usage:
        async with analysis_slot() as acquired:
            if not acquired:
                raise HTTPException(503, "Analysis capacity full")
            # ... run pipeline ...
    """
    global _slots_in_use
    acquired = False
    try:
        try:
            async with asyncio.timeout(timeout):
                await _analysis_semaphore.acquire()
            acquired = True
            _slots_in_use += 1
        except TimeoutError:
            log.warning(
                "analysis_slot_timeout",
                in_use=_slots_in_use,
                limit=MAX_CONCURRENT_ANALYSES,
            )
        yield acquired
    finally:
        if acquired:
            _slots_in_use -= 1
            _analysis_semaphore.release()


async def acquire_analysis_slot() -> bool:
    """Try to acquire an analysis slot. Returns False if would block too long.

    Legacy API: prefer `async with analysis_slot()` for cancellation safety.
    Callers MUST call release_analysis_slot() in a finally block after True.
    """
    global _slots_in_use
    try:
        async with asyncio.timeout(_ACQUIRE_TIMEOUT):
            await _analysis_semaphore.acquire()
        _slots_in_use += 1
        return True
    except TimeoutError:
        log.warning(
            "analysis_slot_timeout",
            in_use=_slots_in_use,
            limit=MAX_CONCURRENT_ANALYSES,
        )
        return False


def release_analysis_slot() -> None:
    """Release an analysis slot.

    Legacy API: prefer `async with analysis_slot()` for cancellation safety.
    """
    global _slots_in_use
    try:
        _analysis_semaphore.release()
        _slots_in_use -= 1
    except ValueError:
        log.error(
            "analysis_slot_over_release",
            in_use=_slots_in_use,
            limit=MAX_CONCURRENT_ANALYSES,
        )
