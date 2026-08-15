# ADR-007: Circuit Breaker Thresholds

**Status:** Accepted  
**Date:** 2025-04-10

## Context

OpenRouter's free tier has unpredictable availability. Models go offline without warning, rate limits are enforced inconsistently, and Nvidia's free workers return `ResourceExhausted` errors during peak hours. Without protection, a burst of failed requests would exhaust the entire rate limit budget (20 req/min) on calls that have no chance of succeeding.

The circuit breaker needs to balance two concerns: protect the rate budget from being wasted on a dead provider, but recover quickly when the provider stabilizes (which is often within seconds for transient blips).

## Decision

Sliding-window circuit breaker with these parameters (configured in `backend/src/agent/circuit_breaker.py`):

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `failure_threshold` | 5 | Trip after 5 failures in window |
| `window_seconds` | 60.0 | Sliding window matches rate limit window |
| `recovery_seconds` | 30.0 | Half the window, fast recovery for transient issues |

State machine: `CLOSED` (normal) -> `OPEN` (all calls rejected) -> `HALF_OPEN` (single probe allowed).

The half-open state uses an async lock to prevent thundering herd: only one coroutine gets the probe slot. Others see the circuit as CLOSED (optimistic transition) and proceed normally. If the probe fails, `_on_failure` re-opens the circuit.

Rate limiter exhaustion (timeout waiting for a slot) raises `CircuitBreakerOpen` with a 5-second retry but does NOT count as a failure toward the circuit breaker threshold. This distinction is important: throttling is expected behavior, not a provider failure.

## Reasons

- **5 failures, not 3.** With 3 sequential calls per debate and the 4-second inter-call delay, a single bad minute could produce 3 failures from one analysis attempt. Threshold of 5 ensures we don't trip from a single analysis timing out, only from a genuine provider outage.
- **60-second window matches rate limit period.** OpenRouter measures rate limits per minute. Aligning the circuit breaker window means one bad minute opens the circuit, protecting the next minute's budget.
- **30-second recovery is fast enough.** Free-tier outages are typically either very short (10-30s, worker recycling) or very long (hours, model taken offline). 30s catches the short ones without over-waiting.
- **Lock prevents thundering herd.** Without it, 3 coroutines (bull, bear, CIO) could all see HALF_OPEN simultaneously and all make probe calls, wasting 3 rate limit slots on a potentially dead provider.

## Consequences

**Positive:**
- Rate limit budget is protected during sustained outages
- Fast recovery (30s) means minimal user impact for transient blips
- Thundering herd prevention is built into the state machine
- Separate treatment of rate limiter exhaustion vs provider failure prevents false trips

**Negative:**
- May over-protect during exactly-5-failure scenarios that are transient. Users wait 30s unnecessarily. In practice, transient issues resolve in <10s and rarely hit the threshold.
- Single probe in half-open means recovery takes at least one full request cycle to confirm. During this time, any new analysis will get stale cache data.
- The 5-failure threshold means the first 5 failed requests in a window are "wasted." On free tier, that's 25% of the per-minute budget. Acceptable tradeoff vs the alternative (no protection, entire budget wasted).
