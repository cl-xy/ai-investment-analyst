import os
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

DB_PATH = (
    Path(os.environ.get("MCP_DATA_DIR", str(Path.home() / ".mcp_investment"))) / "portfolio.db"
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS positions (
    ticker      TEXT PRIMARY KEY,
    shares      REAL NOT NULL,
    cost_basis  REAL NOT NULL,
    sector      TEXT NOT NULL DEFAULT 'Unknown',
    added_date  TEXT NOT NULL DEFAULT (date('now'))
)
"""


@asynccontextmanager
async def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(CREATE_TABLE)
        await db.commit()
        yield db


async def fetch_all_positions() -> list[dict]:
    async with _db() as db:
        cursor = await db.execute("SELECT * FROM positions ORDER BY ticker")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def upsert_position(ticker: str, shares: float, cost_basis: float, sector: str) -> None:
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
            (ticker.upper(), shares, cost_basis, sector),
        )
        await db.commit()


async def delete_position(ticker: str) -> bool:
    async with _db() as db:
        cursor = await db.execute("DELETE FROM positions WHERE ticker = ?", (ticker.upper(),))
        await db.commit()
        return cursor.rowcount > 0


async def update_position_fields(
    ticker: str, shares: float | None, cost_basis: float | None
) -> bool:
    updates = []
    params = []
    if shares is not None:
        updates.append("shares = ?")
        params.append(shares)
    if cost_basis is not None:
        updates.append("cost_basis = ?")
        params.append(cost_basis)
    if not updates:
        return False
    params.append(ticker.upper())
    async with _db() as db:
        cursor = await db.execute(
            f"UPDATE positions SET {', '.join(updates)} WHERE ticker = ?", params
        )
        await db.commit()
        return cursor.rowcount > 0
