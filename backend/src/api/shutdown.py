"""Graceful shutdown coordination for in-flight SSE streams."""

import asyncio

from src.logging_config import get_logger

log = get_logger("shutdown")


class ShutdownCoordinator:
    """Tracks active analysis streams and drains on shutdown."""

    def __init__(self, drain_timeout: float = 30.0):
        self._active_streams: set[asyncio.Task] = set()
        self._draining = False
        self._drain_timeout = drain_timeout

    @property
    def is_draining(self) -> bool:
        return self._draining

    @property
    def active_count(self) -> int:
        return len(self._active_streams)

    def register(self, task: asyncio.Task) -> None:
        self._active_streams.add(task)
        task.add_done_callback(self._active_streams.discard)

    async def drain(self) -> None:
        """Wait for active streams to finish, up to timeout."""
        self._draining = True
        if not self._active_streams:
            log.info("drain_complete", active=0)
            return

        log.info("draining", active=len(self._active_streams), timeout=self._drain_timeout)
        done, pending = await asyncio.wait(
            self._active_streams, timeout=self._drain_timeout
        )
        if pending:
            log.warning("drain_timeout", cancelled=len(pending))
            for task in pending:
                task.cancel()
        else:
            log.info("drain_complete", finished=len(done))


# Module-level singleton
shutdown_coordinator = ShutdownCoordinator()
