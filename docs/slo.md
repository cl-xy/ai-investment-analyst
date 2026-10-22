# Service Level Objectives

Objectives for the AI Investment Analyst production deployment. These SLOs reflect the constraints of a free-tier architecture (OpenRouter, Neon, Fly.io) and are calibrated for a portfolio piece with occasional demo traffic, not sustained production load.

## Availability

**Target:** 99.5% measured over a rolling 7-day window.

**Measurement:** Health check endpoint (`/api/health`) pinged every 60 seconds. Success = HTTP 200 with valid JSON response containing `status: "healthy"` and database connectivity confirmed. Results stored in the `health_checks` table in PostgreSQL.

**Calculation:** `(successful_checks / total_checks) * 100` over 7 days = 10,080 checks. 99.5% allows up to 50 failed checks (~50 minutes of downtime per week).

**Exclusions:** Scheduled Fly.io machine restarts (auto-stop/start behavior) are excluded if the machine responds within 10s of the first request (cold start).

## Latency

### Analysis Latency (end-to-end)

| Percentile | Target | Notes |
|------------|--------|-------|
| p50 | < 150s | Typical: 3 LLM turns at 20-45s each + data fetch + report. Measured p50 since the primary model change: 140s |
| p95 | < 220s | A slow primary turn hands over to a reasoning-off hedge after 25s. Measured p95: 202s |
| p99 | < 300s | Hard route limit: 75s setup + 180s analysis + 45s report. Measured p99: 206s |

**Measurement:** Elapsed time from SSE connection open (`analysis_started` event) to `analysis_complete` event. Logged in structured request logs with `request_id`, `ticker`, `duration_ms` fields.

**Note:** These targets reflect the 3-agent debate architecture with free-tier models, whose speed varies a lot from hour to hour. The earlier targets (p50 90s, p95 150s, p99 180s) predate the current primary model; 43 stored live runs since 20 October 2026 (excluding cache and error paths, including degraded results) measured p50 140s, p95 202s, max 206s. The targets above are set just above those measurements and should be revisited with more data. A turn that cannot finish produces a degraded result (recorded with trace status `degraded`) rather than failing the request, and does not count against availability.

### API Response Latency (non-analysis endpoints)

| Endpoint | p95 Target |
|----------|-----------|
| `GET /api/health` | < 100ms |
| `GET /api/signals/history` | < 500ms |
| `POST /api/analyze` (cache hit) | < 200ms |

## Cache Performance

**Cache hit rate target:** > 60% for repeat ticker queries within the TTL window.

**Measurement:** Cache hit/miss counters logged per request. Calculated as `cache_hits / (cache_hits + cache_misses)` over a rolling 24-hour window. Only counts requests for tickers that have been analyzed at least once (first-time tickers are always misses by definition).

**Breakdown by source:**
- Market quotes (yfinance): expect 70%+ hit rate (15min fresh TTL, popular tickers repeat)
- News (NewsAPI): expect 50%+ hit rate (6hr fresh TTL)
- SEC filings: expect 95%+ hit rate (7-day fresh TTL, filings don't change)

## Error Budget

**Monthly error budget:** 0.5% = 3.6 hours equivalent downtime per 30-day period.

**Budget consumption:** each minute of unavailability (failed health check) consumes `1 / (30 * 24 * 60 * 0.005)` = 0.046% of the monthly budget.

### Burn Rate Alerting

| Burn Rate | Window | Meaning | Action |
|-----------|--------|---------|--------|
| 14.4x | 1 hour | Budget exhausted in 12 hours at this rate | Page: investigate immediately |
| 6x | 6 hours | Budget exhausted in 5 days at this rate | Alert: investigate within 1 hour |
| 1x | 3 days | On track to exhaust budget this month | Warning: review during business hours |

**Note:** "Page" in this context means a Fly.io alert notification. There's no on-call rotation for a portfolio piece, but the alert structure demonstrates production-grade thinking.

## Measurement Infrastructure

All metrics are derived from:

1. **Structured logs** (Python `logging` with JSON formatter): every request logs `request_id`, `duration_ms`, `status_code`, `cache_hit`, `circuit_breaker_state`.
2. **PostgreSQL tables**: `health_checks` (availability), `analyses` (latency), `cache` (hit rate).
3. **Fly.io metrics**: machine uptime, restart count, memory/CPU utilization.

There is no separate metrics service (Prometheus/Grafana). SLO tracking is done via SQL queries against the existing PostgreSQL database. This is sufficient for current traffic levels (<100 analyses/day).

## Remediation Playbook

### Availability breach (< 99.5% over 7 days)

1. Check Fly.io machine status: `fly status --app ai-investment-analyst`
2. Check logs for crash loops: `fly logs --app ai-investment-analyst`
3. Verify Neon database connectivity (most common cause of health check failure)
4. If machines are healthy but health checks fail: check DATABASE_URL secret, Neon may have rotated credentials
5. Redeploy if binary is corrupted: `git push` triggers CI/CD rebuild

### Latency breach (p95 > 220s)

1. Check circuit breaker state in logs (search for `circuit_opened` events)
2. Verify OpenRouter model availability at status.openrouter.ai
3. Look at the per-attempt records stored with recent traces (`traces.llm_attempts`, or the `llm_attempt_timeout` and `llm_hedge_*` log lines): if the primary keeps hitting its 45s cap with no content, the provider is slow and turns are being hedged or degraded. The system does not fall back to a single-shot analysis; check the fallback chain in `backend/src/config.py` and `backend/src/agent/llm_fallback.py`
4. If latency is high but models respond: check for database connection pool exhaustion (too many concurrent cache reads)

### Cache hit rate breach (< 60%)

1. Check if cache table was truncated (Neon free tier has auto-vacuum behavior)
2. Verify background refresh tasks are running (search logs for `cache.refresh`)
3. Check if TTL config was accidentally shortened
4. High miss rate after deploy is expected (cold cache). Allow 24-48 hours to warm before alerting.
