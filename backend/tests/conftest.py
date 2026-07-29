"""Root conftest: reset shared state between tests to prevent ordering pollution."""

import pytest


@pytest.fixture(autouse=True)
def _reset_concurrency_semaphore():
    """Reset the analysis semaphore before each test to prevent slot leaks."""
    from src.agent.concurrency import _analysis_semaphore

    # Reset to full capacity (3 slots)
    while _analysis_semaphore._value < 3:
        _analysis_semaphore.release()
    # Drain any excess (shouldn't happen, but defensive)
    while _analysis_semaphore._value > 3:
        _analysis_semaphore._value -= 1
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the slowapi rate limiter storage between tests."""
    from src.middleware.auth import limiter

    yield
    # Clear rate limit state after each test
    if hasattr(limiter, "_storage") and hasattr(limiter._storage, "reset"):
        limiter._storage.reset()
    # For in-memory storage, just clear the internal dict
    storage = getattr(limiter, "_storage", None)
    if storage and hasattr(storage, "storage"):
        storage.storage.clear()
    elif storage and hasattr(storage, "_cache"):
        storage._cache.clear()
