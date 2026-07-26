"""Tests for the shutdown coordinator module."""

import asyncio

import pytest

from src.api.shutdown import ShutdownCoordinator


@pytest.fixture
def coordinator():
    """Create a fresh shutdown coordinator for each test."""
    return ShutdownCoordinator(drain_timeout=1.0)


class TestShutdownCoordinator:
    def test_starts_not_draining(self, coordinator):
        assert coordinator.is_draining is False
        assert coordinator.active_count == 0

    @pytest.mark.asyncio
    async def test_register_tracks_active_tasks(self, coordinator):
        async def slow_work():
            await asyncio.sleep(10)

        task = asyncio.create_task(slow_work())
        coordinator.register(task)
        assert coordinator.active_count == 1

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # done_callback should have removed it
        await asyncio.sleep(0.01)
        assert coordinator.active_count == 0

    @pytest.mark.asyncio
    async def test_drain_waits_for_tasks(self, coordinator):
        completed = False

        async def quick_work():
            nonlocal completed
            await asyncio.sleep(0.05)
            completed = True

        task = asyncio.create_task(quick_work())
        coordinator.register(task)

        await coordinator.drain()

        assert completed is True
        assert coordinator.is_draining is True

    @pytest.mark.asyncio
    async def test_drain_timeout_cancels_remaining(self):
        coordinator = ShutdownCoordinator(drain_timeout=0.05)

        async def stuck_work():
            await asyncio.sleep(100)

        task = asyncio.create_task(stuck_work())
        coordinator.register(task)

        await coordinator.drain()

        # Allow the event loop to process the cancellation
        await asyncio.sleep(0.01)

        assert coordinator.is_draining is True
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_drain_with_no_tasks(self, coordinator):
        # Should complete immediately without errors
        await coordinator.drain()
        assert coordinator.is_draining is True

    @pytest.mark.asyncio
    async def test_is_draining_flag_set_on_drain(self, coordinator):
        assert coordinator.is_draining is False
        await coordinator.drain()
        assert coordinator.is_draining is True

    @pytest.mark.asyncio
    async def test_multiple_tasks_tracked(self, coordinator):
        tasks = []
        for _ in range(5):

            async def work():
                await asyncio.sleep(0.01)

            task = asyncio.create_task(work())
            coordinator.register(task)
            tasks.append(task)

        assert coordinator.active_count == 5

        await coordinator.drain()
        assert coordinator.active_count == 0
