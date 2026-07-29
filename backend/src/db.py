"""
PostgreSQL connection pool and query helpers.

Uses asyncpg for async database access. Connection pool is initialized
on first use and shared across the application lifecycle.
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg
from asyncpg import Pool

from src.config import settings

log = logging.getLogger(__name__)

_pool: Pool | None = None
_pool_lock = asyncio.Lock()


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Validate each connection when acquired from the pool."""
    # Lightweight query to detect stale connections (Neon closes idle ones)
    await conn.execute("SELECT 1")


async def get_pool() -> Pool:
    """Get or create the connection pool (double-checked locking)."""
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                for attempt in range(3):
                    try:
                        _pool = await asyncpg.create_pool(
                            settings.database_url,
                            min_size=1,
                            max_size=10,
                            # Close idle connections before Neon's 5-min timeout kills them
                            max_inactive_connection_lifetime=120.0,
                            command_timeout=30.0,
                        )
                        break
                    except (OSError, asyncpg.PostgresError) as exc:
                        if attempt == 2:
                            raise
                        log.warning("pool_create_retry attempt=%d error=%s", attempt + 1, exc)
                        await asyncio.sleep(1.0 * (attempt + 1))
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
    thesis          TEXT NOT NULL DEFAULT '',
    bull_case       JSONB NOT NULL DEFAULT '[]',
    bear_case       JSONB NOT NULL DEFAULT '[]',
    news_summary    TEXT NOT NULL DEFAULT '',
    risk_flags      JSONB NOT NULL DEFAULT '[]',
    price_data      JSONB NOT NULL DEFAULT '{}',
    fundamentals    JSONB NOT NULL DEFAULT '{}',
    sec_notes       TEXT NOT NULL DEFAULT '',
    debate          JSONB,
    verdict_rationale TEXT NOT NULL DEFAULT '',
    key_disagreements JSONB NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_ticker_analyses_ticker ON ticker_analyses(ticker);
CREATE INDEX IF NOT EXISTS idx_ticker_analyses_analysis_id ON ticker_analyses(analysis_id);

-- Predictions (Layer 3: track record and calibration)
CREATE TABLE IF NOT EXISTS predictions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id     UUID REFERENCES analyses(id) ON DELETE SET NULL,
    ticker          TEXT NOT NULL,
    signal          TEXT NOT NULL,
    confidence      TEXT NOT NULL,
    sentiment_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    thesis          TEXT NOT NULL DEFAULT '',
    price_at_prediction DOUBLE PRECISION,
    horizon_days    INTEGER NOT NULL DEFAULT 30,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ,
    outcome_price   DOUBLE PRECISION,
    realized_return DOUBLE PRECISION,
    outcome         TEXT  -- 'correct', 'incorrect', 'neutral', NULL if unresolved
);
CREATE INDEX IF NOT EXISTS idx_predictions_ticker ON predictions(ticker);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON predictions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_unresolved ON predictions(resolved_at) WHERE resolved_at IS NULL;

-- Runs (cost/latency tracking)
CREATE TABLE IF NOT EXISTS runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            TEXT UNIQUE NOT NULL,
    tickers           TEXT[] NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL,
    completed_at      TIMESTAMPTZ,
    duration_ms       INTEGER NOT NULL DEFAULT 0,
    router_model      TEXT NOT NULL DEFAULT 'openai/gpt-oss-20b:free',
    analysis_model    TEXT NOT NULL DEFAULT 'nvidia/nemotron-3-super-120b-a12b:free',
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


MIGRATIONS_SQL = """
-- Columns added after initial ticker_analyses table creation.
-- ADD COLUMN IF NOT EXISTS is idempotent, safe to run every startup.
ALTER TABLE ticker_analyses ADD COLUMN IF NOT EXISTS thesis TEXT NOT NULL DEFAULT '';
ALTER TABLE ticker_analyses ADD COLUMN IF NOT EXISTS bull_case JSONB NOT NULL DEFAULT '[]';
ALTER TABLE ticker_analyses ADD COLUMN IF NOT EXISTS bear_case JSONB NOT NULL DEFAULT '[]';
ALTER TABLE ticker_analyses ADD COLUMN IF NOT EXISTS debate JSONB;
ALTER TABLE ticker_analyses ADD COLUMN IF NOT EXISTS verdict_rationale TEXT NOT NULL DEFAULT '';
ALTER TABLE ticker_analyses ADD COLUMN IF NOT EXISTS key_disagreements JSONB NOT NULL DEFAULT '[]';
ALTER TABLE ticker_analyses ADD COLUMN IF NOT EXISTS earnings JSONB NOT NULL DEFAULT '{}';

-- Traces table for replay system
CREATE TABLE IF NOT EXISTS traces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          TEXT NOT NULL,
    tickers         TEXT[] NOT NULL,
    events          JSONB NOT NULL,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'success',
    signal          TEXT,
    is_featured     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_traces_created_at ON traces(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_traces_tickers ON traces USING GIN(tickers);
CREATE INDEX IF NOT EXISTS idx_traces_featured ON traces(is_featured) WHERE is_featured = TRUE;

-- Ops dashboard: detailed traces with correlation IDs and per-stage breakdowns
CREATE TABLE IF NOT EXISTS ops_traces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    correlation_id  TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'success',
    events          JSONB NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_ops_traces_correlation_id ON ops_traces(correlation_id);
CREATE INDEX IF NOT EXISTS idx_ops_traces_ticker ON ops_traces(ticker);
CREATE INDEX IF NOT EXISTS idx_ops_traces_created_at ON ops_traces(created_at DESC);

-- Ops dashboard: periodic metrics snapshots for SLO computation
CREATE TABLE IF NOT EXISTS ops_metrics_snapshots (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metrics     JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_ops_metrics_snapshots_recorded_at ON ops_metrics_snapshots(recorded_at DESC);
"""


async def init_schema() -> None:
    """Create tables if they don't exist, then apply column migrations."""
    pool = await get_pool()
    await pool.execute(SCHEMA_SQL)
    await pool.execute(MIGRATIONS_SQL)
