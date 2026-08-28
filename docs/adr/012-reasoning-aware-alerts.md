# ADR-012: Reasoning-Aware Signal Alerts

**Status:** Accepted
**Date:** 2026-08-24

## Context

The system already runs scheduled re-analyses (`/api/scheduled/refresh-portfolio`, `/api/scheduled/refresh-earnings`), but these silently update the cache. There was no mechanism to notify a user when a monitored ticker's underlying investment thesis had materially changed, and no alert history.

Every mainstream broker app (IBKR, Schwab, Robinhood) alerts on *price* or *volume* thresholds: "NVDA dropped 5%." That's a dumb signal — it tells you the number moved, not whether the *argument* behind holding the position still holds. Given the system already produces structured, citation-backed bull/bear/moderator debates (`backend/src/agent/debate_schemas.py`), it has something almost no consumer tool has: a machine-readable investment thesis it can diff against new evidence.

I needed a way to (a) detect when new evidence arrives for a monitored ticker, (b) decide whether that evidence is material enough to warrant interrupting the user, and (c) notify them somewhere they'll actually see it in real time — without blowing through the OpenRouter free-tier budget by re-running a full debate on every check.

## Decision

Built a two-tier drift-detection pipeline (`backend/src/alerts/`) with Telegram delivery:

1. **Event triggers** (`triggers/`) — four independent, cheap checks per ticker: a new SEC 8-K/10-Q filed since the last analysis, a StockTwits sentiment swing, a >5% price move against the price recorded at analysis time, and a sector peer's signal flipping (via the existing static `SECTOR_PEERS` map — zero extra network calls).

2. **Heuristic drift scorer** (`drift_scorer.py`) — a pure, weighted function (`score_drift`) combining sentiment delta, price move, risk-flag count change, filing detection, news volume spike, and peer flip into a single score in `[0, 1]`. No I/O, no LLM. Runs on every monitored ticker on every evaluation pass.

3. **LLM drift judge** (`drift_judge.py`) — invoked *only* when the heuristic score clears a threshold (default 0.4). A single call to the fast/cheap router model (`llm_router_model`, 20B — not the 120B debate model) asks: "given what changed, would the verdict actually change?" Budget-gated via the existing `use_budget("openrouter")` atomic check-and-consume; if the budget is exhausted, the pipeline still fires a heuristic-only alert rather than blocking.

4. **Composer** (`composer.py`) — turns the drift score + optional LLM judgment into a severity-tagged `Alert` (info/warning/critical) with a structured `reasoning_diff` (which arguments shifted, not just which number moved), persisted to Postgres.

5. **Telegram dispatch** (`telegram.py`) — single bot-per-deployment model. Users `/start` the bot to register a `chat_id`; alerts are pushed with the signal transition, key reasoning shifts, and a deep link back into the app. Rate-limited to one alert per ticker per 4 hours.

6. **Scheduling** — a new `POST /api/scheduled/evaluate-alerts` endpoint (same auth/lock/timeout pattern as the existing scheduled routes) triggered by a GitHub Actions cron restricted to US market hours, plus a fire-and-forget hook after a successful portfolio refresh.

## Reasons

- **Heuristic-first is a direct cost control, not just an optimization.** The system already runs on OpenRouter's free tier (20 req/min) with a daily budget guard. Running an LLM call on every scheduled check for every monitored ticker would exhaust that budget on background monitoring alone, starving the interactive analysis flow the product is actually for. Gating the LLM call behind a cheap heuristic pre-filter means the expensive path only runs when there's a real chance something changed.
- **Structural diffing over price thresholds is the actual product differentiation.** Any broker app can tell you the price moved. Almost none can tell you *why the argument that justified the position might no longer hold* — because almost none run a structured, citation-backed debate in the first place. This alert system exists specifically because the debate schemas already produce that structure; it would be wasted if nothing consumed it after the initial analysis.
- **Telegram over email/push.** Push notifications need a service worker and platform-specific setup; email has minutes of latency and gets buried. Telegram's Bot API is a single HTTP call away (already have `httpx`), supports rich formatting and deep links, and — pragmatically — lets a reviewer connect their own Telegram and see a live alert during a demo, which email can't do as immediately.
- **Single bot, not per-user OAuth.** This is a portfolio-scale demo, not a multi-tenant SaaS. A single bot token that any number of users `/start` is orders of magnitude simpler than building Telegram OAuth, and the security model (webhook secret token, fails closed) is still correct for that scale.
- **Sector-peer contamination reuses an existing static map.** The peer trigger deliberately does not do a fresh sector lookup — it reuses `SECTOR_PEERS` from the pre-existing peer-comparison feature and the already-persisted `ticker_analyses` history, so this trigger costs nothing extra in API calls.

## Consequences

**Positive:**

- Alerts carry a structured `reasoning_diff` (drift components, triggered events, LLM key_shifts) instead of a bare price delta — directly answers "why does this alert exist" in the UI and in the Telegram message.
- LLM cost for the alert pipeline is bounded: only tickers that clear the heuristic threshold ever trigger a model call, and that call is on the cheap router model, not the debate model.
- The pipeline degrades gracefully at every layer: a failed probe source doesn't fail the whole evaluation; a budget-exhausted LLM judge still produces a (lower-severity) alert instead of silence; a failed Telegram dispatch doesn't fail persistence.
- Both portfolio positions and opt-in watchlist tickers are monitored through the same `evaluate_all_monitored()` path, so the alert surface grows for free as users add tickers to their watchlist.

**Negative:**

- The heuristic scorer's weights (sentiment 0.25, price 0.20, risk-flags 0.20, filing 0.15, news volume 0.10, peer flip 0.10) are hand-tuned, not learned from outcome data — unlike the calibration/track-record system, there's no feedback loop yet that checks whether escalated alerts actually preceded a real signal change.
- Single-bot Telegram means every registered chat gets every alert; there's no per-user ticker subscription filtering at the dispatch layer (filtering happens at the subscription/monitoring layer instead, so a user who isn't monitoring a ticker won't generate an alert for it — but if they *are* monitoring it, they get it regardless of who else is too).
- The peer-signal trigger's "baseline" (what a peer's signal was "around the time of our own last analysis") is a coarse `created_at <=` lookup, not a true point-in-time snapshot join — acceptable for a demo-scale feature, but not something to rely on for precise backtesting.
- Reasoning drift detection only fires for tickers with at least one prior successful analysis (`get_last_analysis` returns `None` otherwise) — a newly-added ticker with no analysis history is silently skipped rather than surfaced as "insufficient baseline," which could look like the feature isn't working on a fresh ticker.
