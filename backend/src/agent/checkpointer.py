"""
Shared LangGraph checkpoint helpers.

Centralizes the SQLite checkpointer path so it isn't hardcoded in 4+ places.
"""

from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

CHECKPOINTER_PATH = "data/checkpointer.db"


def get_checkpointer() -> AsyncSqliteSaver:
    """Create an async SQLite checkpointer (use as async context manager).

    Usage:
        async with get_checkpointer() as checkpointer:
            compiled = graph.compile(checkpointer=checkpointer)
    """
    Path("data").mkdir(exist_ok=True)
    return AsyncSqliteSaver.from_conn_string(CHECKPOINTER_PATH)
