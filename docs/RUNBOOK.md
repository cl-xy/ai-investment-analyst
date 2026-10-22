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
| OpenRouter dashboard | `https://openrouter.ai` |

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

# LLM attempts, hedging and provider blocks (see section 10)
fly logs -a ai-investment-analyst | grep -E 'llm_attempt_|llm_hedge_|stocktwits_blocked|yfinance_rate_limited|serving_stale'
```

**Quick health validation:**

```bash
curl -s https://<app-domain>/api/health | jq .
curl -s https://<app-domain>/api/health/ready | jq .
```

---

## 1. OpenRouter API 429 (Rate Limited)

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

# Check OpenRouter dashboard for usage
# https://openrouter.ai -> Usage tab
```

**Mitigation**:
- Circuit breaker auto-activates after 5 failures in 60s (30s recovery cooldown)
- Stale-while-revalidate cache serves the most recent cached analysis for any ticker that has been analyzed before
- No manual intervention needed for transient spikes
- If sustained: reduce concurrency limit temporarily by redeploying with lower `MAX_CONCURRENT_ANALYSES`

**Prevention**:
- Budget guards track daily OpenRouter call counts
- Concurrency limiter (max 3 simultaneous pipelines) throttles burst demand
- Consider upgrading to OpenRouter paid tier if demo traffic grows

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
- Alpha Vantage: 20/day (budget limit in config). Reserve 5 for manual use.

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
- `response_format={"type": "json_object"}` (OpenRouter JSON mode)
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

## 7. Cold Cache / Slow First Analysis

**Symptoms**:
- First analysis of a ticker takes 30s+ because nothing is cached yet
- Report banner says data is cached or unavailable for a source

**Diagnosis**:

```bash
curl -s https://<app-domain>/api/health | jq .

# Manual test: time an analysis
time curl -s "https://<app-domain>/api/analyze/stream?tickers=AAPL" > /dev/null

# Which providers failed on a run
fly logs --app ai-investment-analyst | grep -E "yfinance_rate_limited|stocktwits_blocked|serving_stale_on_error"
```

**Mitigation**:
- Run the analysis once; later runs are served from the Postgres cache
- If Yahoo is rate limiting, the last good value is served with its age shown in the banner

**Prevention**:
- Cache TTLs are long enough that a stale entry is served while one background refresh runs
- Stale-if-error keeps the last good value for a limited time when a provider fails

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
- Fly.io default signal handling (SIGTERM with platform-managed kill timeout)
- Shutdown coordinator registered with signal handlers
- Frontend handles 503 + Retry-After by showing "server updating, retrying shortly"
- Consider adding explicit `kill_signal` and `kill_timeout` to `backend/fly.toml` for longer grace periods

---

## 9. Signal Alerts Not Firing / Telegram Not Delivering

**Symptoms**:
- No alerts appear on `/alerts` despite monitored tickers having obvious news/price moves
- Telegram bot doesn't respond to `/start`, or dispatched alerts never arrive
- `alerts` table stays empty after `evaluate-alerts` runs

**Diagnosis**:

```bash
# Manually trigger an evaluation pass and inspect the response
curl -X POST https://<app-domain>/api/scheduled/evaluate-alerts \
  -H "x-scheduler-token: $SCHEDULER_SECRET_TOKEN" | jq .
# Look at tickers_evaluated / alerts_fired / llm_calls_used in the response

fly logs -a ai-investment-analyst | grep 'alert_evaluation\|alert_pipeline\|telegram_'

# Check which tickers are actually monitored
curl -s "https://<app-domain>/api/alerts/subscriptions?password=$DEMO_PASSWORD" | jq .
```

**Common root causes**:
- **No prior analysis for the ticker.** `evaluate_ticker` skips (`skip_reason=no_prior_analysis`) any ticker that has never completed a successful debate — run one analysis first before expecting drift detection.
- **Heuristic score never crosses the threshold (0.4 default).** Check `drift_score` in the `alerts` table or `reasoning_diff.components` on a persisted alert (if one fired at all) — small moves are intentionally filtered out to avoid noise.
- **OpenRouter budget exhausted.** `judge_drift` returns `skip_reason=budget_exhausted` and the alert still fires but stays heuristic-only (`llm_judged=false`, severity capped at `warning`). Check `/api/ops` budget panel.
- **`TELEGRAM_BOT_TOKEN` / `TELEGRAM_WEBHOOK_SECRET` not configured.** `dispatch_alert` logs `telegram_call_skipped_no_token` and silently no-ops — alerts still persist and show in `/alerts`, they just never reach Telegram.
- **No registered chats.** A user must `/start` the bot at least once; `get_active_chat_ids()` returning empty means `dispatch_alert` returns 0 sent with no error.
- **4-hour per-ticker cooldown.** `alert_dispatch_state` rate-limits Telegram sends to once per ticker per 4h regardless of severity — check `last_dispatched_at` for the ticker if a second alert seems suppressed.

**Mitigation**:
- Verify the webhook is registered: `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
- Re-register if needed: `https://api.telegram.org/bot<TOKEN>/setWebhook?url=<BACKEND_URL>/api/telegram/webhook&secret_token=<TELEGRAM_WEBHOOK_SECRET>`
- Force a test dispatch bypassing the cooldown by calling `dispatch_alert(alert, force=True)` from a one-off script if you need to confirm delivery end-to-end

**Prevention**:
- `.github/workflows/alert-evaluation.yml` runs every 2h during US market hours; use `workflow_dispatch` to trigger on demand for testing
- The `refresh-portfolio` success hook (`_evaluate_alerts_best_effort`) piggybacks a full evaluation pass on every successful portfolio refresh, so alerts stay reasonably fresh even if the dedicated cron is delayed

## 10. Debate Turn Degraded or Slow (primary model stalls)

**Symptoms**:
- A card shows "Based on partial data" with a line such as "bear agent failed: LLM attempt exceeded 8s wall-clock timeout"
- The trace status is `degraded` in `/api/ops/traces`
- Runs take over 200 seconds
- The card says "Answered in fast mode" or "Answered by a backup model"

**What is happening**: the primary model is a reasoning model. Its hidden thinking has no upper bound (20s to over 100s observed), and a reply often arrives as one chunk at the end. A turn that stalls is hedged and falls back as described in `docs/ARCHITECTURE.md` ("LLM Calls"). A turn that no model can finish produces a degraded card.

**Diagnosis**:

```bash
# Per-attempt records stored with the run (survive after logs rotate; no prompt or output text)
curl -s -H "Authorization: Bearer <session-token>" https://<app-domain>/api/replay/<trace-id> | jq '.llm_attempts'

# Live log lines (about 8 minutes retained when queried): timing, finish reason, answering model
fly logs -a ai-investment-analyst | grep -E 'llm_attempt_(ok|timeout|stalled)|llm_hedge_|llm_chain_|moderator_|bear_|bull_'
```

In `llm_attempts`, each entry has `role`, `model`, `mode` (`reasoning_on` or `reasoning_off`), `outcome` (`ok`, `timeout`, `stalled`, `cancelled`, `error:...`), `slice_s`, `elapsed_s`, `first_chunk_s`, `first_content_s` and `finish`. A `reasoning_on` timeout with many chunks but no content means the model was thinking; a backup with zero chunks means the provider stalled.

**Mitigation**:
- Re-run the analysis; most degraded runs succeed on a second attempt
- If the provider is slow for hours, nothing in the application is broken. The knobs are in `backend/src/config.py`: `llm_attempt_timeout_seconds` (45), `llm_hedge_after_seconds` (25, 0 disables), `llm_backup_first_output_seconds` (15, 0 disables), `debate_ticker_budget_seconds` (165). Raising the attempt cap shifts time away from later turns and does not make the provider faster.

**Known gaps**:
- Whether a reasoning-off bear turn skews verdicts toward `buy` is unresolved (4 of 15 runs with one ended `buy`, against 0 of 24 without), and the groups were not matched
- `finish_reason=length` replies are logged but their repair outcome is not
- Retail sentiment (StockTwits) is blocked by Cloudflare in production, so that source is nearly always empty and does not raise the banner

---
