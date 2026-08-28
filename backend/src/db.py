"""
PostgreSQL connection pool and query helpers.

Uses asyncpg for async database access. Connection pool is initialized
on first use and shared across the application lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, TypeVar

import asyncpg
from asyncpg import Pool

from src.config import settings

log = logging.getLogger(__name__)

_pool: Pool | None = None
_pool_lock: asyncio.Lock | None = None

# Transient connection errors worth retrying once (Neon idle kills, network blips)
_RETRYABLE = (
    asyncpg.ConnectionDoesNotExistError,
    asyncpg.InterfaceError,
    asyncpg.PostgresConnectionError,
    ConnectionResetError,
    ConnectionError,
    OSError,
)

T = TypeVar("T")


def _get_lock() -> asyncio.Lock:
    """Lazily create the lock on the running event loop (avoids 3.10+ binding issues)."""
    global _pool_lock
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    return _pool_lock


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Run once per physical connection creation (codecs, session settings)."""
    # Placeholder for any per-connection setup (type codecs, search_path, etc.)
    pass


async def _check_connection(conn: asyncpg.Connection) -> None:
    """Validate connection on each acquire from pool (detects Neon idle kills)."""
    await conn.execute("SELECT 1")


async def get_pool() -> Pool:
    """Get or create the connection pool (double-checked locking)."""
    global _pool
    if _pool is None:
        async with _get_lock():
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
                            init=_init_connection,
                            setup=_check_connection,
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
    async with _get_lock():
        if _pool is not None:
            await _pool.close()
            _pool = None


async def _with_retry(fn: Callable[..., Coroutine[Any, Any, T]], *args: Any) -> T:
    """Execute a pool operation with one retry on transient connection errors."""
    pool = await get_pool()
    try:
        return await fn(pool, *args)
    except _RETRYABLE as exc:
        log.warning("db_retry query=%s error=%s", args[0] if args else "?", exc)
        # Re-acquire from pool (setup callback will validate the new connection)
        pool = await get_pool()
        return await fn(pool, *args)


async def execute(query: str, *args) -> str:
    """Execute a query and return the status."""
    return await _with_retry(lambda p, q, *a: p.execute(q, *a), query, *args)


async def fetch(query: str, *args) -> list[asyncpg.Record]:
    """Fetch multiple rows."""
    return await _with_retry(lambda p, q, *a: p.fetch(q, *a), query, *args)


async def fetchrow(query: str, *args) -> asyncpg.Record | None:
    """Fetch a single row."""
    return await _with_retry(lambda p, q, *a: p.fetchrow(q, *a), query, *args)


async def fetchval(query: str, *args):
    """Fetch a single value."""
    return await _with_retry(lambda p, q, *a: p.fetchval(q, *a), query, *args)


async def executemany(query: str, args: list[tuple]) -> None:
    """Execute a query for multiple rows (batch insert). Atomic: all-or-nothing."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(query, args)


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

-- Per-ticker cost attribution tracking
CREATE TABLE IF NOT EXISTS cost_attribution (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    correlation_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cost_attribution_ticker ON cost_attribution(ticker);
CREATE INDEX IF NOT EXISTS idx_cost_attribution_created ON cost_attribution(created_at);

-- Evidence Integrity Ledger: immutable artifact storage
CREATE TABLE IF NOT EXISTS evidence_artifacts (
    artifact_id     TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    provider        TEXT NOT NULL,
    tool            TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    cache_hit       BOOLEAN NOT NULL DEFAULT FALSE,
    payload_excerpt TEXT NOT NULL DEFAULT '',
    payload_size    INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (artifact_id, run_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_artifacts_run_id ON evidence_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_artifacts_ticker ON evidence_artifacts(ticker);
CREATE INDEX IF NOT EXISTS idx_evidence_artifacts_content_hash ON evidence_artifacts(content_hash);

-- Citation validation results per run
CREATE TABLE IF NOT EXISTS citation_validations (
    run_id          TEXT PRIMARY KEY,
    validation_data JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Distributed run ownership (replaces per-process _in_flight_tickers)
CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id          TEXT PRIMARY KEY,
    ticker          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running',
    owner_machine   TEXT NOT NULL,
    lease_expires   TIMESTAMPTZ NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    CONSTRAINT status_check CHECK (status IN ('running', 'completed', 'failed', 'abandoned'))
);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_ticker_status ON analysis_runs(ticker, status);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_lease ON analysis_runs(lease_expires) WHERE status = 'running';
CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_runs_active_ticker ON analysis_runs(ticker) WHERE status = 'running';

-- Distributed rate limiter (replaces per-process TokenBucket)
CREATE TABLE IF NOT EXISTS rate_limit_state (
    scope           TEXT PRIMARY KEY,
    tokens          DOUBLE PRECISION NOT NULL,
    capacity        DOUBLE PRECISION NOT NULL,
    refill_rate     DOUBLE PRECISION NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Initialize OpenRouter rate limit bucket (20 req/min = 0.333 req/sec)
INSERT INTO rate_limit_state (scope, tokens, capacity, refill_rate)
VALUES ('openrouter', 10, 10, 0.333)
ON CONFLICT (scope) DO UPDATE SET
    capacity = EXCLUDED.capacity,
    refill_rate = EXCLUDED.refill_rate;

-- Enhanced calibration: add benchmark and adjusted-price columns
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS benchmark_return DOUBLE PRECISION;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS excess_return DOUBLE PRECISION;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS adj_price_at_prediction DOUBLE PRECISION;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS adj_outcome_price DOUBLE PRECISION;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS resolution_method TEXT NOT NULL DEFAULT 'adjusted_close';

-- Reasoning-Aware Signal Alerts: watchlist-opt-in monitoring subscriptions.
-- Portfolio positions (SQLite `positions` table) are implicitly monitored;
-- this table additionally covers frontend-watchlist-only tickers that opt in.
CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'watchlist',
    trigger_types   JSONB NOT NULL DEFAULT '["sec", "sentiment", "peer", "price"]',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT alert_subscriptions_source_check CHECK (source IN ('portfolio', 'watchlist'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_subscriptions_ticker_active
    ON alert_subscriptions(ticker) WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_active ON alert_subscriptions(active) WHERE active = TRUE;

-- Reasoning-Aware Signal Alerts: alert history with structured reasoning diffs.
CREATE TABLE IF NOT EXISTS alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker              TEXT NOT NULL,
    alert_type          TEXT NOT NULL,
    severity            TEXT NOT NULL DEFAULT 'info',
    drift_score         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    old_signal          TEXT,
    new_signal          TEXT,
    reasoning_diff      JSONB NOT NULL DEFAULT '{}',
    triggered_by        JSONB NOT NULL DEFAULT '[]',
    llm_judged          BOOLEAN NOT NULL DEFAULT FALSE,
    dispatched_telegram BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at     TIMESTAMPTZ,
    CONSTRAINT alerts_severity_check CHECK (severity IN ('info', 'warning', 'critical'))
);
CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON alerts(ticker);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unacknowledged ON alerts(acknowledged_at) WHERE acknowledged_at IS NULL;

-- Reasoning-Aware Signal Alerts: Telegram bot chat registrations (single bot,
-- multiple subscribers). last_alert_sent_at is keyed per-ticker in the
-- dispatcher's rate limiter, not here; this just tracks registration state.
CREATE TABLE IF NOT EXISTS telegram_registrations (
    chat_id             BIGINT PRIMARY KEY,
    registered_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    last_alert_sent_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_telegram_registrations_active ON telegram_registrations(active) WHERE active = TRUE;

-- Per-ticker Telegram dispatch rate limiting (max 1 alert per ticker per 4h,
-- independent of chat_id since there's one bot but potentially many chats).
CREATE TABLE IF NOT EXISTS alert_dispatch_state (
    ticker              TEXT PRIMARY KEY,
    last_dispatched_at  TIMESTAMPTZ NOT NULL
);
"""


async def init_schema() -> None:
    """Create tables if they don't exist, then apply column migrations."""
    pool = await get_pool()
    await pool.execute(SCHEMA_SQL)
    await pool.execute(MIGRATIONS_SQL)
