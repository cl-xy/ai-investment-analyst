import asyncio
import math
import os
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from src.validation import validate_ticker

DB_PATH = (
    Path(os.environ.get("MCP_DATA_DIR", str(Path.home() / ".mcp_investment"))) / "portfolio.db"
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS positions (
    ticker      TEXT PRIMARY KEY,
    shares      REAL NOT NULL,
    cost_basis  REAL NOT NULL,
    sector      TEXT NOT NULL DEFAULT 'Unknown',
    added_date  TEXT NOT NULL DEFAULT (date('now'))
)
"""

_initialized = False
_init_lock = asyncio.Lock()


async def _ensure_schema(db: aiosqlite.Connection) -> None:
    """Run schema creation exactly once per process."""
    global _initialized  # noqa: PLW0603
    if _initialized:
        return
    async with _init_lock:
        if _initialized:
            return
        await db.execute(_CREATE_TABLE)
        await db.commit()
        _initialized = True


def _validate_ticker(ticker: str) -> str:
    """Normalize and validate ticker input."""
    return validate_ticker(ticker)


def _validate_positive(value: float, field: str) -> float:
    """Validate that a numeric field is finite and non-negative."""
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{field} must be finite")
    if value < 0:
        raise ValueError(f"{field} must not be negative")
    return float(value)


@asynccontextmanager
async def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await _ensure_schema(db)
        yield db


async def fetch_all_positions() -> list[dict]:
    async with _db() as db:
        cursor = await db.execute("SELECT * FROM positions ORDER BY ticker")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def upsert_position(ticker: str, shares: float, cost_basis: float, sector: str) -> None:
    clean_ticker = _validate_ticker(ticker)
    _validate_positive(shares, "shares")
    _validate_positive(cost_basis, "cost_basis")
    if not isinstance(sector, str) or not sector.strip():
        raise ValueError("sector must be a non-empty string")
    async with _db() as db:
        await db.execute(
            """
            INSERT INTO positions (ticker, shares, cost_basis, sector)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                shares     = excluded.shares,
                cost_basis = excluded.cost_basis,
                sector     = excluded.sector
            """,
            (clean_ticker, shares, cost_basis, sector.strip()),
        )
        await db.commit()


async def delete_position(ticker: str) -> bool:
    clean_ticker = _validate_ticker(ticker)
    async with _db() as db:
        cursor = await db.execute("DELETE FROM positions WHERE ticker = ?", (clean_ticker,))
        await db.commit()
        return cursor.rowcount > 0


async def update_position_fields(
    ticker: str, shares: float | None, cost_basis: float | None
) -> bool:
    clean_ticker = _validate_ticker(ticker)
    updates = []
    params: list[float | str] = []
    if shares is not None:
        _validate_positive(shares, "shares")
        updates.append("shares = ?")
        params.append(shares)
    if cost_basis is not None:
        _validate_positive(cost_basis, "cost_basis")
        updates.append("cost_basis = ?")
        params.append(cost_basis)
    if not updates:
        return False
    params.append(clean_ticker)
    async with _db() as db:
        cursor = await db.execute(  # nosemgrep: sql-string-interpolation
            f"UPDATE positions SET {', '.join(updates)} WHERE ticker = ?", params
        )
        await db.commit()
        return cursor.rowcount > 0
