"""Global concurrency limits for analysis runs."""

import asyncio

from src.logging_config import get_logger

log = get_logger("concurrency")

# Max concurrent full analysis pipelines per instance
_analysis_semaphore = asyncio.Semaphore(3)


async def acquire_analysis_slot() -> bool:
    """Try to acquire an analysis slot. Returns False if would block too long."""
    try:
        await asyncio.wait_for(_analysis_semaphore.acquire(), timeout=5.0)
        return True
    except asyncio.TimeoutError:
        log.warning("analysis_slot_timeout", available=_analysis_semaphore._value)
        return False


def release_analysis_slot() -> None:
    """Release an analysis slot."""
    _analysis_semaphore.release()
