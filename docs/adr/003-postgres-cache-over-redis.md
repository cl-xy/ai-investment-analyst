# ADR-003: PostgreSQL Cache Over Redis

**Status:** Accepted  
**Date:** 2025-03-20

## Context

LLM analyses are expensive in both latency (60-120s) and rate limit budget (3 calls per ticker). Repeated requests for the same ticker within a reasonable window should serve cached results. Market data from yfinance and news from NewsAPI also benefit from caching to reduce external API calls and improve response times.

The caching layer needs: per-source TTLs (quotes refresh faster than SEC filings), stale-while-revalidate semantics (serve stale data while refreshing in background), and JSONB storage for heterogeneous response shapes.

Options considered: Redis, PostgreSQL JSONB, in-memory LRU.

## Decision

Use PostgreSQL with a stale-while-revalidate pattern. Implementation in `backend/src/cache/manager.py` with per-source TTL configuration:

- `yfinance:get_quote`: fresh 15min, stale 1hr, expire 4hr
- `yfinance:get_fundamentals`: fresh 24hr, stale 48hr, expire 7d
- `sec_edgar:get_latest_filing_summary`: fresh 7d, stale 30d, never expire
- `newsapi:get_ticker_news`: fresh 6hr, stale 12hr, expire 24hr
- `stocktwits:get_ticker_sentiment`: fresh 30min, stale 1hr, expire 4hr

Three states: **fresh** (serve directly), **stale** (serve immediately + trigger background refresh), **expired** (must refetch).

## Reasons

- **One fewer service to operate.** Already running Neon PostgreSQL for analyses, predictions, and budget tracking. Adding Redis means another managed service, another connection pool, another failure mode.
- **JSONB supports flexible schemas.** Tool responses have different shapes (quotes vs filings vs news). JSONB stores them without schema migrations. Indexing on cache key is sufficient.
- **Transactional consistency.** Cache writes can participate in the same transaction as analysis result writes. No distributed cache invalidation issues.
- **Neon free tier is sufficient.** 0.5GB storage, 3GB transfer. Cache entries are small JSON documents. Well within limits for a portfolio piece.
- **Stale-while-revalidate is the right pattern.** Users get instant responses for repeat queries while data refreshes in the background. Market data that's 20 minutes old is better than a 2-minute wait for fresh data.

## Consequences

**Positive:**
- Single database dependency simplifies deployment, monitoring, and backup
- Cache entries are queryable (useful for debugging: "what's cached for NVDA?")
- Background refresh is just an asyncio task, no pub/sub infrastructure needed
- Budget guards can check cache before deciding whether to spend an API call

**Negative:**
- Higher read latency than Redis (~5-10ms vs ~1ms). Acceptable for this workload where the alternative is a 60-120s LLM call.
- No built-in TTL expiration (unlike Redis EXPIRE). Handled with a periodic cleanup query and checked on read.
- Connection pool is shared between cache reads and primary queries. Under high load, cache reads could contend with analysis writes. Mitigated by Neon's connection pooling.
