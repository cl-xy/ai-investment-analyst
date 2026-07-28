"""
PostgreSQL connection pool and query helpers.

Uses asyncpg for async database access. Connection pool is initialized
on first use and shared across the application lifecycle.
"""

from __future__ import annotations

import asyncio

import asyncpg
from asyncpg import Pool

from src.config import settings

_pool: Pool | None = None
_pool_lock = asyncio.Lock()


async def get_pool() -> Pool:
    """Get or create the connection pool (double-checked locking)."""
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    settings.database_url,
                    min_size=2,
                    max_size=10,
                )
    return _pool


async def close_pool() -> None:
    """Close the connection pool (call on shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def execute(query: str, *args) -> str:
    """Execute a query and return the status."""
    pool = await get_pool()
    return await pool.execute(query, *args)


async def fetch(query: str, *args) -> list[asyncpg.Record]:
    """Fetch multiple rows."""
    pool = await get_pool()
    return await pool.fetch(query, *args)


async def fetchrow(query: str, *args) -> asyncpg.Record | None:
    """Fetch a single row."""
    pool = await get_pool()
    return await pool.fetchrow(query, *args)


async def fetchval(query: str, *args):
    """Fetch a single value."""
    pool = await get_pool()
    return await pool.fetchval(query, *args)


SCHEMA_SQL = """
-- Analyses
CREATE TABLE IF NOT EXISTS analyses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tickers         TEXT[] NOT NULL,
    report_markdown TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ticker_analyses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id     UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    signal          TEXT NOT NULL DEFAULT 'insufficient_data',
    confidence      TEXT NOT NULL DEFAULT 'low',
    sentiment_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    news_summary    TEXT NOT NULL DEFAULT '',
    risk_flags      JSONB NOT NULL DEFAULT '[]',
    price_data      JSONB NOT NULL DEFAULT '{}',
    fundamentals    JSONB NOT NULL DEFAULT '{}',
    sec_notes       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ticker_analyses_ticker ON ticker_analyses(ticker);
CREATE INDEX IF NOT EXISTS idx_ticker_analyses_analysis_id ON ticker_analyses(analysis_id);

-- Runs (cost/latency tracking)
CREATE TABLE IF NOT EXISTS runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            TEXT UNIQUE NOT NULL,
    tickers           TEXT[] NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL,
    completed_at      TIMESTAMPTZ,
    duration_ms       INTEGER NOT NULL DEFAULT 0,
    router_model      TEXT NOT NULL DEFAULT 'openai/gpt-oss-20b',
    analysis_model    TEXT NOT NULL DEFAULT 'openai/gpt-oss-120b',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    tool_calls        INTEGER NOT NULL DEFAULT 0,
    tool_successes    INTEGER NOT NULL DEFAULT 0,
    tool_failures     INTEGER NOT NULL DEFAULT 0,
    cache_hits        INTEGER NOT NULL DEFAULT 0,
    cache_misses      INTEGER NOT NULL DEFAULT 0,
    cost_usd          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    schema_valid      BOOLEAN NOT NULL DEFAULT TRUE,
    citations_count   INTEGER NOT NULL DEFAULT 0,
    data_gaps_count   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);

-- Budget (daily API usage tracking)
CREATE TABLE IF NOT EXISTS budget (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider    TEXT NOT NULL,
    date        DATE NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(provider, date)
);

-- Cache (stale-while-revalidate)
CREATE TABLE IF NOT EXISTS cache (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key         TEXT UNIQUE NOT NULL,
    data        JSONB NOT NULL,
    source_id   TEXT NOT NULL,
    provider    TEXT NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL,
    stale_at    TIMESTAMPTZ NOT NULL,
    expires_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_cache_expires_at ON cache(expires_at) WHERE expires_at IS NOT NULL;
"""


async def init_schema() -> None:
    """Create tables if they don't exist. Called on app startup."""
    pool = await get_pool()
    await pool.execute(SCHEMA_SQL)
