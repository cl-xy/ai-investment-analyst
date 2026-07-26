# Runbook

Operational playbook for the AI Investment Analyst. Each scenario includes symptoms, diagnosis, mitigation, and prevention.

## Quick Reference

| Resource | Location |
|----------|----------|
| Fly.io dashboard | `https://fly.io/apps/ai-investment-analyst` |
| Neon dashboard | `https://console.neon.tech` (project: ai-investment-analyst) |
| Vercel dashboard | `https://vercel.com/cl-xy/ai-investment-analyst` |
| Health check | `GET /api/health` (liveness) |
| Readiness check | `GET /api/health/ready` (includes DB connectivity) |
| Groq console | `https://console.groq.com` |

**Key log queries** (structured JSON logs via structlog):

```bash
# Fly.io logs (recent)
fly logs -a ai-investment-analyst

# Filter for errors
fly logs -a ai-investment-analyst | grep '"level":"error"'

# Circuit breaker events
fly logs -a ai-investment-analyst | grep 'circuit_'

# Rate limit hits
fly logs -a ai-investment-analyst | grep '429'
```

**Quick health validation:**

```bash
curl -s https://<app-domain>/api/health | jq .
curl -s https://<app-domain>/api/health/ready | jq .
```

---

## 1. Groq API 429 (Rate Limited)

**Symptoms**:
- Analyses failing mid-stream
- Circuit breaker tripping (logs show `circuit_opened`)
- SSE stream emits error events with "rate limit" or "429" context
- Multiple users reporting simultaneous failures

**Diagnosis**:

```bash
# Check recent 429s in logs
fly logs -a ai-investment-analyst --since 10m | grep '429'

# Check circuit breaker state (if exposed via health)
curl -s https://<app-domain>/api/health | jq .

# Check Groq dashboard for usage
# https://console.groq.com -> Usage tab
```

**Mitigation**:
- Circuit breaker auto-activates after 5 failures in 60s (30s recovery cooldown)
- Stale-while-revalidate cache serves the most recent cached analysis for any ticker that has been analyzed before
- No manual intervention needed for transient spikes
- If sustained: reduce concurrency limit temporarily by redeploying with lower `MAX_CONCURRENT_ANALYSES`

**Prevention**:
- Budget guards track daily Groq call counts
- Cache warming for demo tickers (AAPL, MSFT, GOOGL, NVDA, TSLA) via nightly cron
- Concurrency limiter (max 3 simultaneous pipelines) throttles burst demand
- Consider upgrading to Groq paid tier if demo traffic grows

---

## 2. Neon PostgreSQL Connection Exhausted

**Symptoms**:
- Slow queries or timeouts on analysis persistence
- Health readiness endpoint returns 503 (`"database": "unreachable"`)
- Logs show connection timeout or pool exhaustion errors
- Cached results stop being served

**Diagnosis**:

```bash
# Check readiness probe
curl -s https://<app-domain>/api/health/ready | jq .

# Check Neon dashboard for connection count
# https://console.neon.tech -> Project -> Monitoring

# Check Fly.io app status
fly status -a ai-investment-analyst

# Look for connection errors in logs
fly logs -a ai-investment-analyst | grep -i 'connection\|pool\|timeout'
```

**Mitigation**:
- Restart the app to release stuck connections:
  ```bash
  fly apps restart ai-investment-analyst
  ```
- Neon serverless driver auto-recovers connections on next query attempt
- If Neon itself is down: analyses still run (just not cached), circuit breaker does not trip for DB failures

**Prevention**:
- Connection pool limits set in config (`max_connections` in asyncpg pool)
- All DB operations use `finally` blocks for proper connection release
- Neon auto-suspends idle compute (no leaked connections from idle instances)
- Monitor Neon connection count in dashboard, alert at 80% capacity

---

## 3. SSE Stream Disconnects

**Symptoms**:
- Frontend shows "connection lost" or analysis stops mid-way
- Partial results displayed (some tickers analyzed, others missing)
- Browser dev tools show EventSource reconnecting
- Fly.io proxy logs show timeout or early close

**Diagnosis**:

```bash
# Check for proxy timeouts
fly logs -a ai-investment-analyst | grep -i 'timeout\|disconnect\|proxy'

# Verify heartbeat is being sent (should see every 15s)
curl -N https://<app-domain>/api/analyze/stream?tickers=AAPL 2>&1 | head -20

# Check if the issue is client-side or server-side
# Client-side: only affects specific users/networks
# Server-side: affects all concurrent users
```

**Mitigation**:
- Client auto-reconnects via EventSource built-in reconnection
- 15s heartbeat keeps connection alive through proxies and load balancers
- If Fly.io proxy is killing connections: verify `X-Accel-Buffering: no` header is present in responses
- For persistent issues: check Fly.io machine placement (restart may land on healthier host)

**Prevention**:
- 15s heartbeat interval configured (`HEARTBEAT_INTERVAL = 15`)
- Response headers: `X-Accel-Buffering: no`, `Cache-Control: no-cache`, `Connection: keep-alive`
- Execution timeout (120s) prevents infinite hanging streams
- Frontend implements exponential backoff on reconnection (not naive retry)

---

## 4. Tool Server Failure (yfinance, NewsAPI, SEC EDGAR)

**Symptoms**:
- `tool_result` SSE events with `success: false`
- `data_gaps` field populated in analysis output
- Analysis completes but with reduced quality (missing price data, no news, no filings)
- Specific provider errors in logs

**Diagnosis**:

```bash
# Identify which provider is failing
fly logs -a ai-investment-analyst | grep 'tool_result.*success.*false'

# Check external service status
# yfinance: try a direct query
curl -s "https://query1.finance.yahoo.com/v8/finance/chart/AAPL" | head -c 200

# NewsAPI: check status
curl -s "https://newsapi.org/v2/everything?q=test&apiKey=$NEWS_API_KEY" | jq .status

# SEC EDGAR: check availability
curl -s "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=apple&type=10-K&output=atom" | head -c 200
```

**Mitigation**:
- Analysis continues with available data (graceful degradation by design)
- `data_gaps` field informs the user what data was unavailable
- Cached tool results serve as fallback for previously-fetched data
- Each tool call is wrapped in try/except; one failure does not crash the pipeline

**Prevention**:
- yfinance: no rate limit, but Yahoo may block IPs. Use residential proxy if needed.
- NewsAPI: 100/day on free tier. Budget tracking prevents exhaustion.
- SEC EDGAR: 10 req/sec limit. Respect with rate limiter. Cache filings permanently (they don't change).
- Alpha Vantage: 25/day. Reserve 5 for manual use.

---

## 5. LLM Producing Invalid JSON

**Symptoms**:
- Pydantic validation errors in logs
- SSE stream shows retry events
- `analysis_complete` events with partial or missing fields
- Increased token usage (retry doubles the cost)

**Diagnosis**:

```bash
# Check for validation errors
fly logs -a ai-investment-analyst | grep -i 'validation\|pydantic\|json'

# Check if it's a specific ticker causing issues (complex companies sometimes confuse the model)
fly logs -a ai-investment-analyst | grep 'retry'

# Check if max_tokens is being hit (truncation = invalid JSON)
fly logs -a ai-investment-analyst | grep 'finish_reason'
```

**Mitigation**:
- Single automatic retry: validation errors are sent back to the model with the schema, asking it to fix the output
- If retry also fails: partial extraction returns whatever valid fields were parsed
- The system never silently returns invalid data; `analysis_complete` event only fires after successful validation

**Prevention**:
- `max_tokens` always set on LLM calls (prevents truncation)
- `response_format={"type": "json_object"}` (Groq JSON mode)
- Full Pydantic schema included in system prompt
- Smaller, simpler schemas have higher success rates. If failures spike, check whether the schema grew too complex.

---

## 6. Deployment Rollback (Fly.io)

**When to rollback**: New deploy causes error rate spike, health checks failing, or SSE streams broken.

**Commands**:

```bash
# List recent releases
fly releases -a ai-investment-analyst

# Rollback to previous release
fly deploy -a ai-investment-analyst --image registry.fly.io/ai-investment-analyst:deployment-<PREVIOUS_ID>

# Or use release number
fly releases rollback -a ai-investment-analyst

# Verify after rollback
curl -s https://<app-domain>/api/health | jq .
curl -s https://<app-domain>/api/health/ready | jq .

# Test SSE stream end-to-end
curl -N "https://<app-domain>/api/analyze/stream?tickers=AAPL" 2>&1 | head -30
```

**Verification checklist**:
- [ ] Health endpoint returns `{"status": "ok"}`
- [ ] Readiness endpoint confirms database connectivity
- [ ] SSE stream produces events (heartbeat at minimum)
- [ ] Frontend can complete a full analysis flow

**Prevention**:
- Always test Docker build locally before pushing: `docker compose up --build`
- Run `pytest -q --tb=short` before deploy
- Fly.io zero-downtime deploys: new machine healthy before old one stops
- Keep previous 3 images available for quick rollback

---

## 7. Cache Warming Failure

**Symptoms**:
- First-time users hit cold-start latency (30s+ per ticker analysis)
- Demo tickers (AAPL, MSFT, GOOGL) not in cache
- GitHub Actions cron job shows failures
- Scheduler token expired or rotated

**Diagnosis**:

```bash
# Check GitHub Actions for cache-warm job status
# https://github.com/cl-xy/ai-investment-analyst/actions

# Check if cache has recent entries
curl -s https://<app-domain>/api/health | jq .

# Manual test: time an analysis
time curl -s "https://<app-domain>/api/analyze/stream?tickers=AAPL" > /dev/null
```

**Mitigation**:
- Trigger manual cache warm:
  ```bash
  curl -X POST https://<app-domain>/api/admin/warm-cache \
    -H "Authorization: Bearer $SCHEDULER_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"tickers": ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]}'
  ```
- If scheduler token expired: regenerate and update GitHub Actions secret

**Prevention**:
- Nightly cron in GitHub Actions triggers cache warm for demo tickers
- Cache TTL set long enough that nightly refresh keeps entries fresh
- Alert on GitHub Actions failure (email notification on cron job failure)
- Scheduler token stored as GitHub Actions secret, rotated quarterly

---

## 8. Graceful Shutdown Issues

**Symptoms**:
- In-flight analyses cut off during deploys
- Users see sudden disconnection without error event
- Logs show `SIGTERM` followed immediately by connection resets

**Diagnosis**:

```bash
# Check shutdown coordinator behavior
fly logs -a ai-investment-analyst | grep -i 'drain\|shutdown\|sigterm'

# Verify drain period is sufficient
fly logs -a ai-investment-analyst | grep 'draining'
```

**Mitigation**:
- Shutdown coordinator sets `is_draining = True` on SIGTERM
- New requests receive 503 with `Retry-After: 10` header
- In-flight analyses get grace period to complete
- If analyses are being cut off: increase Fly.io kill timeout in `fly.toml`

**Prevention**:
- `kill_signal = "SIGTERM"` and `kill_timeout = 30` in fly.toml
- Shutdown coordinator registered with signal handlers
- Frontend handles 503 + Retry-After by showing "server updating, retrying shortly"
