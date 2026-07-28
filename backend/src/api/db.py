"""
Backward-compatibility shim. The canonical module is now src.db.

All imports should use `from src.db import ...` directly.
"""

from src.db import (  # noqa: F401
    SCHEMA_SQL,
    close_pool,
    execute,
    fetch,
    fetchrow,
    fetchval,
    get_pool,
    init_schema,
)
