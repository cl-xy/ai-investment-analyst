"""
Shared LangGraph checkpoint helpers.

Centralizes the SQLite checkpointer path so it isn't hardcoded in 4+ places.
"""

import os
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Resolve from env var or default to data/checkpointer.db relative to project root
# (project root = backend/, three levels up from this file).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINTER_PATH = os.environ.get(
    "CHECKPOINTER_PATH",
    str(_PROJECT_ROOT / "data" / "checkpointer.db"),
)

# Ensure the parent directory exists once at import time rather than on every call.
Path(CHECKPOINTER_PATH).parent.mkdir(parents=True, exist_ok=True)


def get_checkpointer() -> AsyncSqliteSaver:
    """Create an async SQLite checkpointer (use as async context manager).

    Usage:
        async with get_checkpointer() as checkpointer:
            compiled = graph.compile(checkpointer=checkpointer)
    """
    return AsyncSqliteSaver.from_conn_string(CHECKPOINTER_PATH)  # type: ignore[return-value]
