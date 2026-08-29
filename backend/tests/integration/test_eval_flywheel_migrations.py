"""
Migration idempotency test for the Outcome-Grounded Evaluation Flywheel schema.

Runs the real `init_schema()` against a live PostgreSQL instance (the same
`DATABASE_URL` CI already provisions via the `postgres` service in
ci.yml) to verify the new evaluation_cases/evaluation_case_artifacts/
evaluation_runs/evaluation_results DDL is idempotent — i.e. safe to run on
every process startup, matching the existing SCHEMA_SQL/MIGRATIONS_SQL
contract.

Skips (rather than fails) when DATABASE_URL is not configured, so this does
not block local test runs without Postgres available.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not configured; skipping live-Postgres migration test",
)


@pytest.mark.asyncio
async def test_init_schema_is_idempotent():
    from src.db import close_pool, fetch, get_pool, init_schema

    try:
        await get_pool()
        await init_schema()
        # Running twice must not raise (idempotent CREATE/ADD COLUMN IF NOT EXISTS).
        await init_schema()

        expected_tables = {
            "evaluation_cases",
            "evaluation_case_artifacts",
            "evaluation_runs",
            "evaluation_results",
        }
        rows = await fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY($1)
            """,
            list(expected_tables),
        )
        found = {r["table_name"] for r in rows}
        assert found == expected_tables

        # correlation_id column added to predictions must also be idempotent.
        col_row = await fetch(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'predictions' AND column_name = 'correlation_id'
            """
        )
        assert len(col_row) == 1
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_evaluation_cases_state_check_constraint():
    """The CHECK constraint on evaluation_cases.state must reject invalid values."""
    import uuid

    from src.db import close_pool, execute, fetchrow, get_pool, init_schema

    try:
        await get_pool()
        await init_schema()

        # Set up minimal parent rows to satisfy FK constraints.
        analysis_id = await fetchrow(
            "INSERT INTO analyses (tickers) VALUES ($1) RETURNING id", ["TEST"]
        )
        prediction_id = await fetchrow(
            """
            INSERT INTO predictions (analysis_id, ticker, signal, confidence)
            VALUES ($1, $2, 'buy', 'high') RETURNING id
            """,
            analysis_id["id"],
            "TEST",
        )

        with pytest.raises(Exception):
            await execute(
                "INSERT INTO evaluation_cases (prediction_id, ticker, case_hash, state) "
                "VALUES ($1, $2, $3, 'not_a_real_state')",
                prediction_id["id"],
                "TEST",
                str(uuid.uuid4()),
            )
    finally:
        # Best-effort cleanup; test DB is ephemeral in CI but keep local runs clean.
        try:
            await execute("DELETE FROM predictions WHERE ticker = 'TEST'")
            await execute("DELETE FROM analyses WHERE tickers = ARRAY['TEST']")
        except Exception:
            pass
        await close_pool()
