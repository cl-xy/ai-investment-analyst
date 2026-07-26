# ADR-002: PostgreSQL Over MongoDB

**Status:** Accepted
**Date:** 2026-07-03
**Deciders:** cl-xy

## Context

The project initially used MongoDB for caching and analysis storage. As the system matured, I realized the data shapes are well-known and stable: analysis results, cache entries, budget tracking, run metadata. There's no document flexibility being exploited.

Running both MongoDB and SQLite (for portfolio/checkpoints) meant two data stores to manage, two connection pools, two backup strategies.

## Decision

Migrate from MongoDB to PostgreSQL as the single relational data store.

Reasons:

- Schemas are known upfront. Analysis results, cache entries, and budget records all have fixed fields. Document flexibility adds no value here.
- Stale-while-revalidate caching needs atomic upserts (`INSERT ... ON CONFLICT UPDATE`). Postgres handles this natively and atomically.
- asyncpg is mature, well-tested, and fast. The async ecosystem around Postgres in Python is stronger than the MongoDB equivalent.
- One database simplifies operations: single backup target, single connection pool, single migration tool (alembic), single hosting bill (Neon).

## Consequences

**Easier:**
- Single data store to reason about, monitor, and back up.
- Atomic cache operations with proper isolation levels.
- Alembic migrations give version-controlled schema changes.
- Neon provides serverless Postgres with branching for dev/staging.
- Joins across analyses, cache, and budget data become trivial.

**Harder:**
- Migration effort from existing MongoDB collections.
- Schema migrations required for any structural changes (vs MongoDB's implicit schema).
- Slightly more ceremony for nested/semi-structured data (use JSONB columns where needed).
