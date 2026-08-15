"""Postgres-backed distributed coordination.

Replaces per-process primitives (TokenBucket, _in_flight_tickers) with
PostgreSQL-backed coordination that works across multiple Fly.io machines.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from src.db import execute, fetchrow, fetchval

# Machine identity for ownership tracking
_MACHINE_ID = os.environ.get("FLY_MACHINE_ID", f"local-{os.getpid()}")

# Lease duration: if a machine dies, its runs become claimable after this
_LEASE_DURATION = timedelta(seconds=120)


async def try_claim_run(run_id: str, ticker: str) -> bool:
    """Attempt to claim ownership of an analysis run.

    Returns True if this machine owns the run, False if another machine
    already owns it (or a previous run for this ticker is still active).

    Uses a single transaction with row-level locking to prevent TOCTOU races
    where two machines could both observe no active run and both insert.
    """
    from src.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Reclaim stale runs for this ticker (within transaction)
            await conn.execute(
                """UPDATE analysis_runs SET status = 'abandoned'
                   WHERE ticker = $1 AND status = 'running'
                   AND lease_expires < now()""",
                ticker,
            )

            # Check for active run with FOR UPDATE to lock the row
            existing = await conn.fetchrow(
                """SELECT run_id, owner_machine FROM analysis_runs
                   WHERE ticker = $1 AND status = 'running'
                   AND lease_expires >= now()
                   FOR UPDATE""",
                ticker,
            )
            if existing:
                return existing["run_id"] == run_id

            # Try to claim (ON CONFLICT handles run_id collision only)
            result = await conn.fetchval(
                """INSERT INTO analysis_runs (run_id, ticker, status, owner_machine, lease_expires)
                   VALUES ($1, $2, 'running', $3, now() + $4::interval)
                   ON CONFLICT (run_id) DO NOTHING
                   RETURNING run_id""",
                run_id,
                ticker,
                _MACHINE_ID,
                f"{int(_LEASE_DURATION.total_seconds())} seconds",
            )
            return result is not None


async def extend_lease(run_id: str) -> bool:
    """Extend the lease on an owned run. Call periodically (~every 30s).

    Returns False if the run was already reclaimed by another machine.
    """
    result = await fetchval(
        """UPDATE analysis_runs
           SET lease_expires = now() + $2::interval
           WHERE run_id = $1 AND owner_machine = $3 AND status = 'running'
           RETURNING run_id""",
        run_id,
        f"{int(_LEASE_DURATION.total_seconds())} seconds",
        _MACHINE_ID,
    )
    return result is not None


async def complete_run(run_id: str, status: str = "completed") -> None:
    """Mark a run as completed or failed. Releases ownership."""
    await execute(
        """UPDATE analysis_runs
           SET status = $2, completed_at = now()
           WHERE run_id = $1""",
        run_id,
        status,
    )


async def try_consume_rate_token(scope: str = "openrouter") -> tuple[bool, float]:
    """Attempt to consume one rate limit token.

    Uses atomic UPDATE with token bucket math (refill + consume in one query).
    Returns (allowed, retry_after_seconds).

    This is the distributed rate limiter: both Fly machines share this bucket.
    """
    row = await fetchrow(
        """UPDATE rate_limit_state
           SET tokens = LEAST(capacity,
                             tokens + EXTRACT(EPOCH FROM (now() - updated_at)) * refill_rate
                       ) - 1,
               updated_at = now()
           WHERE scope = $1
             AND LEAST(capacity,
                       tokens + EXTRACT(EPOCH FROM (now() - updated_at)) * refill_rate
                 ) >= 1
           RETURNING tokens""",
        scope,
    )

    if row is not None:
        return True, 0.0

    # Denied: calculate retry_after
    state = await fetchrow(
        "SELECT tokens, refill_rate, updated_at FROM rate_limit_state WHERE scope = $1",
        scope,
    )
    if state:
        current_tokens = state["tokens"] + (
            (datetime.now(timezone.utc) - state["updated_at"]).total_seconds()
            * state["refill_rate"]
        )
        tokens_needed = max(0, 1 - current_tokens)
        retry_after = tokens_needed / state["refill_rate"] if state["refill_rate"] > 0 else 3.0
        return False, retry_after

    return False, 3.0


async def get_rate_limit_status(scope: str = "openrouter") -> dict:
    """Get current rate limiter state for ops dashboard."""
    row = await fetchrow(
        "SELECT tokens, capacity, refill_rate, updated_at FROM rate_limit_state WHERE scope = $1",
        scope,
    )
    if not row:
        return {"available": 0, "capacity": 0, "refill_rate": 0}

    elapsed = (datetime.now(timezone.utc) - row["updated_at"]).total_seconds()
    current_tokens = min(row["capacity"], row["tokens"] + elapsed * row["refill_rate"])

    return {
        "available": round(current_tokens, 1),
        "capacity": row["capacity"],
        "refill_rate": row["refill_rate"],
        "updated_at": row["updated_at"].isoformat(),
    }
