# Incident 001: OpenRouter 429 Cascade

**Date:** 2026-03-14
**Duration:** 11 minutes (4 min hard outage, 7 min degraded)
**Severity:** SEV-2 (partial service outage)
**Correlation ID:** `corr_8f3a2b1c-429d-4e5f-9a1b-2c3d4e5f6a7b`

## Summary

A temporary reduction in OpenRouter's free-tier rate limits caused a spike in 429 responses. The circuit breaker counted these as failures, tripped open, and rejected all incoming requests for 3 minutes, including those that would have been served from cache. Users saw "Circuit breaker open" errors despite cached data being available.

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 14:32 | First 429 responses from OpenRouter. Rate limit header shows 10 req/min (down from usual 20). |
| 14:33 | Circuit breaker failure counter reaches threshold (5 failures in 60s window). Breaker trips OPEN. |
| 14:33 | All incoming `/api/analyze` requests rejected with 503 "Circuit breaker open" regardless of cache state. |
| 14:34 | Monitoring alert fires on error rate spike. I check logs, see the 429 cascade pattern. |
| 14:35 | Confirm OpenRouter status page shows "Degraded: Free tier rate limits temporarily reduced." |
| 14:36 | Deploy hotfix: exclude HTTP 429 from circuit breaker failure count. |
| 14:36 | Circuit breaker resets to HALF_OPEN on deploy restart. |
| 14:37 | First successful request passes through. Breaker transitions to CLOSED. |
| 14:37 | Cached responses serving normally again. Live analyses still hitting 429s intermittently. |
| 14:42 | OpenRouter restores normal rate limits. |
| 14:44 | All metrics return to baseline. Incident resolved. |

## Root Cause

The circuit breaker in `backend/src/agent/circuit_breaker.py` treated all non-2xx LLM responses as failures, including HTTP 429 (rate limited). When OpenRouter temporarily halved their free-tier limit from 20 to 10 req/min, the burst of 429s tripped the breaker within 60 seconds.

Once open, the breaker rejected all requests at the middleware level, before the cache lookup. This meant even requests for tickers with warm cache entries (which never need to hit OpenRouter) were blocked.

The core issue: rate limiting is a signal to slow down, not a signal that the service is broken. The circuit breaker conflated "upstream is overwhelmed" with "upstream is failing."

## Impact

- 4 minutes of complete service unavailability (all requests returned 503)
- 7 minutes of degraded service (intermittent 429s on live analyses, cached responses working)
- Approximately 47 unique users affected based on Fly.io access logs
- No data loss or corruption

## Resolution

Immediate (same day):
1. Excluded HTTP 429 from circuit breaker failure count
2. Added separate rate-limit tracking that triggers backoff without tripping the breaker
3. Ensured cached responses bypass the circuit breaker path (cache hit returns early, before breaker is consulted)

Follow-up (next week):
4. Added category-aware failure classification (network errors, server errors, rate limits, timeouts each tracked separately)
5. Circuit breaker now only trips on server errors (5xx) and network failures
6. Rate limit responses trigger adaptive request spacing instead

## Lessons Learned

1. **Rate limits are not failures.** A 429 means "slow down," not "I'm broken." Circuit breakers should only trip on signals that indicate actual service degradation (5xx, timeouts, connection refused).

2. **Cache should be reachable even when upstream is degraded.** The middleware ordering meant the breaker blocked everything, including cache hits that never touch the upstream. Cache lookup must happen before (or independent of) the circuit breaker.

3. **Free-tier services can change limits without notice.** OpenRouter's status page updated after the limit change, not before. We need to handle sudden limit reductions gracefully.

4. **The 60-second window was borderline.** Five failures in 60 seconds is normal variance on a rate-limited free tier. Considered widening the window, but the real fix was removing 429s from the failure count entirely. With only true server errors counting, 5/60s is a reasonable threshold.

## Action Items

| Item | Status | Date |
|------|--------|------|
| Exclude 429 from circuit breaker failure count | Done | 2026-03-14 |
| Move cache lookup before circuit breaker | Done | 2026-03-14 |
| Add rate-limit-specific backoff logic | Done | 2026-03-15 |
| Category-aware failure classification | Done | 2026-03-18 |
| Add integration test: 429 storm does not trip breaker | Done | 2026-03-18 |
| Document circuit breaker behavior in ops runbook | Done | 2026-03-20 |
