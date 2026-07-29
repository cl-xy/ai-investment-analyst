# ADR-004: Free-Tier Architecture

**Status:** Accepted  
**Date:** 2025-03-10

## Context

This project is a portfolio piece. It needs to be live and functional without recurring costs. The primary constraint is OpenRouter's free tier: 20 requests per minute, shared across all models. Secondary constraints: Neon free tier (0.5GB), NewsAPI free tier (100 req/day), SEC EDGAR (10 req/sec).

Rather than stubbing out functionality or using mocks, I wanted to demonstrate real constraint-handling engineering: how does a system behave gracefully when resources are genuinely scarce?

## Decision

Design the entire system around constraint awareness rather than simulating a production environment with unlimited resources. Every layer has explicit degradation behavior:

1. **Circuit breaker** (`backend/src/agent/circuit_breaker.py`): trips at 5 failures within 60s, 30s recovery window, half-open probe with lock to prevent thundering herd.
2. **Rate limiter**: per-IP throttling via slowapi, prevents a single user from exhausting the shared pool.
3. **Budget guards**: daily request counting in PostgreSQL. Alpha Vantage capped at 20/day (save 5 for manual use).
4. **Stale cache serving**: when the circuit breaker is open or rate limit is exhausted, serve stale cached data rather than failing.
5. **Debate fallback**: if the 3-agent debate can't complete (rate limit), fall back to single-shot analysis (1 LLM call instead of 3).
6. **4-second inter-call delay**: minimum gap between sequential LLM calls in debate to avoid burst throttling on free-tier workers.

## Reasons

- **Demonstrates real engineering.** Handling resource scarcity gracefully is harder than throwing money at infrastructure. This is the kind of problem production systems face at scale, just at a smaller magnitude.
- **Zero recurring cost.** Fly.io (2 machines, auto-stop), Neon (free tier), Vercel (hobby), OpenRouter (free models). Total monthly cost: $0.
- **Graceful degradation over hard failure.** Users always get some response, even if it's stale cached data or a simplified single-shot analysis.
- **Constraint-aware UX.** The frontend shows when data is served from cache, when the system is in degraded mode, and estimated wait times.

## Consequences

**Positive:**
- System never crashes due to rate limiting, just degrades gracefully
- Circuit breaker prevents cascade failures from burning remaining budget
- Stale cache means repeat queries are always fast regardless of provider status
- Architecture patterns transfer directly to production cost optimization

**Negative:**
- Analysis takes 90-120s (3 sequential LLM calls with 4s delays between each)
- Under heavy use, users may hit circuit breaker and get stale/degraded results
- Free-tier models (gpt-oss-20b, nemotron-120b) have lower quality than paid alternatives
- No SLA from OpenRouter free tier, availability is best-effort
