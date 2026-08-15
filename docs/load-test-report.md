# Load Test Report

**Date:** 2026-06-15
**Environment:** Production (Fly.io shared-cpu-1x, 512MB RAM, sin region)
**Database:** Neon PostgreSQL (connection pooler, 20 max connections)
**Tool:** Custom async test harness (`scripts/load_test.py`, asyncio + httpx, ~50 lines)
**Duration:** 30 minutes sustained load
**Commit:** `a4f1c82` (main at time of test)

## Methodology

Ran three test phases against the production deployment:

1. **Warm-up (5 min):** Single-threaded requests to populate cache for 8 tickers (AAPL, MSFT, GOOGL, TSLA, NVDA, AMZN, META, JPM).
2. **Sustained load (20 min):** Ramped from 1 to 10 concurrent clients, each making requests in a loop. Mix: 70% cached ticker lookups, 20% SSE stream connections, 10% cold analyses.
3. **Cool-down (5 min):** Reduced to 2 concurrent clients, observed recovery metrics.

Measured via response headers, client-side timing, and Fly.io metrics dashboard. SSE stability measured by tracking heartbeat gaps (>20s gap = connection considered dropped).

## Results Summary

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| API health p95 | <100ms | 23ms | PASS |
| Cached analysis p95 | <200ms | 87ms | PASS |
| Live analysis p95 | <150s | 127s | PASS |
| SSE connection stability | >99.5% | 99.7% | PASS |
| Memory under 10 concurrent SSE | <450MB | 312MB | PASS |
| Cache hit rate (warm) | >60% | 78% | PASS |
| Circuit breaker recovery | <90s | 38s | PASS |
| Error rate (steady state) | <1% | 0.3% | PASS |

**Note:** Live analysis p50 (94s) slightly exceeds the SLO target of <90s under sustained 10-client load. At normal traffic (1-5 clients), p50 is within bounds. Tracking under error budget.

## Detailed Results

### Latency Distribution (cached responses)

| Percentile | Latency |
|------------|---------|
| p50 | 34ms |
| p75 | 52ms |
| p90 | 71ms |
| p95 | 87ms |
| p99 | 143ms |

Cached responses are fast. The p99 spike to 143ms correlates with Neon connection pool contention when all 10 clients hit simultaneously.

### Latency Distribution (live analysis, end-to-end)

| Percentile | Latency |
|------------|---------|
| p50 | 94s |
| p75 | 108s |
| p90 | 119s |
| p95 | 127s |
| p99 | 141s |

Live analysis is dominated by three sequential LLM calls in the debate step (bull, bear, CIO), each taking 25-40s on the free tier. Total wall clock is 90-140s depending on OpenRouter queue depth.

### Throughput Under Load

| Concurrent Clients | Avg Response Time (cached) | Avg Response Time (live) | Error Rate |
|--------------------|---------------------------|--------------------------|------------|
| 1 | 28ms | 89s | 0% |
| 3 | 35ms | 96s | 0% |
| 5 | 44ms | 104s | 0.1% |
| 8 | 61ms | 118s | 0.2% |
| 10 | 73ms | 131s | 0.3% |

Error rate at 10 concurrent comes from occasional OpenRouter 429s when multiple live analyses compete for the 20 req/min budget. Cached responses remain stable regardless of concurrency.

### Memory Profile

| Concurrent SSE Streams | RSS (MB) | tracemalloc (MB) | Notes |
|------------------------|-----------|-----------|-------|
| 0 (idle) | 187 | 142 | Baseline after startup |
| 2 | 223 | 178 | Normal operation |
| 5 | 267 | 214 | Well within budget |
| 8 | 294 | 241 | Starting to see GC pressure |
| 10 | 312 | 258 | Peak observed, stable |
| 10 (sustained 10 min) | 318 | 261 | No leak detected |

Memory stays well within the 512MB limit. Each SSE stream adds roughly 12-15MB (LangGraph state, tool results buffer, response accumulator). No memory leak observed over the 20-minute sustained window. tracemalloc column shows Python-tracked allocations only (excludes C extensions and OS overhead).

### Circuit Breaker Behavior

Induced 100% failure rate on OpenRouter for 30 seconds during test:

| Time | Event |
|------|-------|
| T+0s | Failure injection starts (mock 500s from OpenRouter) |
| T+8s | Circuit breaker trips OPEN (5 failures in window) |
| T+8s | New live analysis requests get 503 immediately (fast fail) |
| T+8s | Cached responses continue serving normally (cache bypass active) |
| T+30s | Failure injection stops |
| T+38s | Half-open probe succeeds (30s recovery timeout elapsed), breaker closes |
| T+38s | Normal operation resumes |

Recovery time: 38 seconds from first failure to full recovery (8s to trip + 30s recovery timeout). During the open period, cached responses were unaffected (confirmed fix from Incident 001).

### Cache Performance

| Time Window | Requests | Hits | Misses | Hit Rate | SWR Serves |
|-------------|----------|------|--------|----------|------------|
| 0-5 min (warm-up) | 8 | 0 | 8 | 0% | 0 |
| 5-10 min | 142 | 108 | 34 | 76% | 12 |
| 10-15 min | 187 | 151 | 36 | 81% | 8 |
| 15-20 min | 203 | 162 | 41 | 80% | 15 |
| 20-25 min | 178 | 136 | 42 | 76% | 19 |

Stale-while-revalidate (SWR) fires correctly: serves stale data immediately while triggering background refresh. The 15-19 SWR serves in later windows correspond to cache entries approaching expiry.

## Failure Injection Results

### Scenario 1: OpenRouter 429 Storm

Injected by sending 25 rapid requests to exhaust the 20 req/min budget.

- Circuit breaker did NOT trip (429s excluded from failure count, per Incident 001 fix)
- Rate limiter activated adaptive backoff: request spacing increased from 0s to 3s between LLM calls
- Cached responses unaffected throughout
- Recovery to normal throughput: 45 seconds after rate limit window reset
- 3 user requests received degraded response (stale cache served via SWR instead of fresh analysis)

### Scenario 2: Database Latency Spike

Added 2000ms simulated delay to all PostgreSQL queries via `pg_sleep(2)` on the connection pooler.

- Cached response p95 jumped from 87ms to 2,134ms (expected: added 2s)
- Live analysis completion time not materially affected (LLM latency dominates; DB is used for cache read/write, trace recording, and cost tracking, but these are non-blocking in the critical path)
- Health endpoint p95 jumped from 23ms to 2,089ms (health check queries the DB)
- No connection pool exhaustion (20 max connections handled the load at 10 concurrent)
- No timeouts (per-tool httpx timeout is 30s for individual MCP calls; SSE/analysis endpoints use a longer 180s timeout to accommodate multi-LLM pipelines)

### Scenario 3: MCP Tool Timeout

Simulated yfinance hanging by injecting 60s delay into the market data tool.

- Analysis timeout triggered at 30s (per-tool timeout setting)
- Tool result marked as `data_gap` in the analysis state
- LLM received partial data and produced analysis noting "market data unavailable"
- Analysis completed in 98s (shorter than normal because it skipped waiting for full market data)
- No cascade: other tools (news, SEC, sentiment) completed independently
- User received analysis with explicit "data gaps" section explaining what was missing

## Conclusions

1. **The system handles its target load comfortably.** 10 concurrent users is well within capacity for the shared-cpu-1x instance. Memory headroom is ~200MB at peak.

2. **Cache is the primary performance lever.** Cached responses are 1000x faster than live analyses. The 78% hit rate means most users get sub-100ms responses.

3. **OpenRouter free tier is the bottleneck for live analyses.** The 20 req/min limit means at most ~6 concurrent live analyses can run without hitting rate limits (each analysis makes 3-4 LLM calls).

4. **Failure isolation works.** Circuit breaker, tool timeouts, and cache bypass all function correctly. A failure in one component doesn't cascade to others.

5. **SSE connections are stable through Fly.io.** The 15s heartbeat interval keeps connections alive. Only 0.3% drop rate over 20 minutes, likely due to client-side network variance.

## Limitations

- Test ran against production with real OpenRouter, so live analysis throughput was constrained by actual rate limits (couldn't test beyond 20 req/min)
- No geographic distribution testing (all requests from sin region, same region as Fly.io deployment)
- Did not test behavior under memory pressure (would need to artificially constrain below 512MB)
- Single-machine test only; did not simulate multi-machine failover
- yfinance timeout scenario was simulated (patched locally), not induced via actual yfinance outage
