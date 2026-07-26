"""
Shared fixtures for integration tests.

Patches module-level singletons (shutdown coordinator, concurrency limiter, DB pool)
to prevent state leakage and lifespan hangs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_patches():
    """Create fresh patch objects for each test invocation."""
    mock_coordinator = MagicMock(
        is_draining=False,
        register=MagicMock(),
        drain=AsyncMock(),
        active_count=0,
        _active_streams=set(),
    )

    return [
        patch("src.api.shutdown.shutdown_coordinator", mock_coordinator),
        patch("src.api.routes.analyze_stream.shutdown_coordinator", mock_coordinator),
        patch(
            "src.api.routes.analyze_stream.acquire_analysis_slot",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("src.api.routes.analyze_stream.release_analysis_slot"),
        patch("src.api.db.get_pool", new_callable=AsyncMock),
        patch("src.api.db.init_schema", new_callable=AsyncMock),
        patch("src.api.db.close_pool", new_callable=AsyncMock),
    ]


@pytest.fixture
def client():
    """
    Per-test client fixture. Creates a fresh TestClient for each test
    with all infrastructure singletons mocked out.
    """
    patches = _make_patches()
    for p in patches:
        p.start()

    try:
        from src.api.main import app

        with TestClient(app) as c:
            yield c
    finally:
        for p in reversed(patches):
            p.stop()
