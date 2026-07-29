# AI Investment Analyst

[![CI](https://github.com/cl-xy/ai-investment-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/cl-xy/ai-investment-analyst/actions/workflows/ci.yml)
[![Uptime](https://img.shields.io/badge/SLO-99.5%25_availability-brightgreen)](docs/slo.md)

> Not a wrapper: observable, degradable, traceable multi-agent LLM pipeline with adversarial debate.

<!-- TODO: Replace with actual recording -->
![Demo](docs/assets/demo-placeholder.gif)

**[Live Demo](https://ai-investment-analyst-iota.vercel.app)** · Password: `investor2026` · [90s Video Walkthrough](#walkthrough)

---

## What to look at in 3 minutes

If you're reviewing this project, here's the guided path:

1. **Click the demo link** → enter password → you'll see a pre-cached NVDA analysis instantly (no 2-min wait)
2. **Open the Ops Dashboard** (`/ops`) → live SLOs, circuit breaker states, rate limit budget, recent errors
3. **Trigger Chaos Mode** → watch the system gracefully degrade (fallback signals, stale cache, circuit breaker tripping)
4. **Open Trace Replay** (`/replay`) → step through a recorded analysis like a debugger (play/pause/rewind)
5. **Read the ADRs** → [`docs/adr/`](docs/adr/) explains why SSE over WebSocket, why adversarial debate, why free-tier constraints shape the architecture
6. **Run a live analysis** → add NVDA to watchlist, click Analyze, watch the full debate stream in real-time (~2 min)

The interesting engineering isn't the features. It's the failure handling, observability, and production judgment underneath.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Frontend (React 19 + Zustand)                     │
│                                                                            │
│  Watchlist → Streaming Analysis → Ops Dashboard → Trace Replay            │
│  EventSource (SSE) ← correlation_id propagated through entire pipeline    │
└───────────────────────────────────┬──────────────────────────────────────┘
                                    │ SSE (domain events, Last-Event-ID)
┌───────────────────────────────────┴──────────────────────────────────────┐
│                          FastAPI Backend (async)                           │
│                                                                            │
│  ┌─── Middleware ───────────────────────────────────────────────────────┐ │
│  │ request_id → auth → rate_limit → cost_tracker → security_headers    │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─── LangGraph StateGraph ─────────────────────────────────────────────┐ │
│  │                                                                       │ │
│  │  Router ──→ Fetch Data ──→ Adversarial Debate ──→ Report ──→ Compare │ │
│  │  (20B)      (5 tools ∥)    Bull → Bear → CIO     (120B)    (if 2+)  │ │
│  │                             (120B x3, sequential)                     │ │
│  │                                                                       │ │
│  │  Circuit Breaker: trip@3 failures, 60s recovery, half-open probe     │ │
│  │  Rate Limiter: token bucket, per-IP + global caps                    │ │
│  │  Budget Guard: daily LLM call ceiling, stale-cache fallback          │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─── Ops Layer ────────────────────────────────────────────────────────┐ │
│  │ Metrics Collector → Trace Recorder → SLO Computer → Chaos Injector  │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└──────┬──────────┬──────────┬──────────┬──────────┬───────────────────────┘
       │          │          │          │          │
  ┌────┴───┐ ┌───┴────┐ ┌───┴───┐ ┌───┴───┐ ┌───┴──────────┐
  │yfinance│ │NewsAPI │ │  SEC  │ │SQLite │ │  PostgreSQL   │
  │ quotes │ │  + RSS │ │EDGAR  │ │portfolio│ │ analyses     │
  │ fundmtl│ │        │ │       │ │       │ │ predictions  │
  │ indctrs│ │        │ │       │ │       │ │ cache (SWR)  │
  └────────┘ └────────┘ └───────┘ └───────┘ │ ops_traces   │
       ↑          ↑          ↑               │ metrics      │
       └──── 4 FastMCP Tool Servers ────┘    └──────────────┘
             (per-tool error isolation)
```

---

## Engineering Tradeoffs

This project is designed around real constraints, not unlimited API budgets:

| Constraint | Impact | Mitigation |
|-----------|--------|------------|
| OpenRouter free tier (20 req/min) | 3 sequential LLM calls = ~2 min per ticker | Circuit breaker + stale cache + graceful degradation to partial analysis |
| Fly.io shared-cpu-1x, 512MB | Can't run Jaeger/Grafana sidecars | In-app ops dashboard, metrics in Postgres, client-side rendering |
| No paid observability platform | No Datadog/New Relic | Custom metrics collector, structured logging with correlation IDs, self-hosted SLO computation |
| Free-tier model quality | Occasional malformed JSON, hallucinated data | JSON mode + Pydantic validation + 1 retry + fallback extraction + data_gaps disclosure |
| Nondeterministic LLM outputs | Hard to test, hard to reproduce bugs | Trace recording + deterministic replay + golden fixture tests + promptfoo eval suite |

Every constraint produced a better architecture than "throw money at it" would have.

---

## What it does

Enter a ticker symbol and watch an adversarial investment committee debate in real-time:

1. **Router** classifies intent and extracts tickers (GPT-OSS 20B, ~100ms)
2. **Fetch Data** calls 5 tools across 4 MCP servers in parallel (market quotes, fundamentals, indicators, news, SEC filings, StockTwits sentiment)
3. **Bull Analyst** builds the strongest possible long case with cited evidence
4. **Bear Analyst** rebuts the bull case point-by-point and argues the short case
5. **Chief Investment Officer** weighs both sides, assesses evidence quality, and issues a final verdict with explicit rationale
6. **Report** generates a cohesive narrative; **Compare** ranks if multiple tickers

Every step streams to the frontend via SSE with domain-specific events. The debate unfolds in real-time with tool call resolution, timing annotations, and citation links.

### Reliability Features

- **Chaos mode**: Inject LLM timeouts, MCP failures, rate exhaustion to demonstrate graceful degradation
- **Trace replay**: Step through any past analysis like a debugger (play/pause/rewind/speed control)
- **Ops dashboard**: Live SLOs, circuit breaker state, budget consumption, error rates
- **Correlation IDs**: Every request traced end-to-end from frontend through LangGraph to MCP tools
- **Circuit breaker**: Trips at 3 consecutive failures, serves cached results, probes recovery
- **Stale-while-revalidate cache**: Never shows "loading" for previously-analyzed tickers

### Track Record

Every signal is a prediction. After 30 days, the system checks the actual market outcome and scores itself:

- Overall accuracy and Brier score (calibration quality)
- Hit rate by confidence bucket (does "high confidence" actually mean high accuracy?)
- Full prediction ledger with wrong calls unhidden

The system is epistemically honest: it shows you when it was wrong.

---

## Key Design Decisions

Detailed rationale in [`docs/adr/`](docs/adr/). Summary:

| Decision | Choice | Why |
|----------|--------|-----|
| Agent orchestration | LangGraph StateGraph | Typed state, conditional edges, checkpointing, astream_events |
| Analysis protocol | Adversarial debate (bull/bear/CIO) | Structured disagreement reduces single-model bias |
| Tool servers | 4x FastMCP (in-process) | Protocol-level interop, per-tool error isolation |
| Streaming | SSE with domain events | Simpler than WS, works through all proxies, built-in reconnection |
| Structured output | JSON mode + Pydantic + retry | Schema validation prevents silent data corruption |
| Caching | PostgreSQL stale-while-revalidate | One fewer service, JSONB flexibility, transactional consistency |
| Observability | Custom in-app (no paid SaaS) | Metrics collector + trace store + SLO computation in Postgres |
| Failure handling | Circuit breaker + graceful degradation | Every layer has a fallback; never crashes, always communicates |

---

## SSE Event Schema

The backend emits domain-specific events (not raw LangGraph internals):

```
run_started       → {tickers, correlation_id}
node_started      → {node_name, correlation_id}
node_completed    → {node_name, duration_ms}
tool_call         → {tool_name, args}
tool_result       → {tool_name, success, cached, duration_ms, source_id}
debate_started    → {ticker, agents}
debate_turn       → {ticker, role, thesis, confidence, key_arguments, turn_index}
debate_verdict    → {ticker, signal, confidence, verdict_rationale, key_disagreements}
analysis_complete → {ticker, analysis}
run_completed     → {total_duration_ms, total_tokens, cost_usd}
heartbeat         → {}  (every 15s, keeps proxies alive)
```

Monotonic sequence IDs enable gapless reconnection via `Last-Event-ID`.

---

## Stack

**Backend**: Python 3.11, FastAPI, LangGraph, FastMCP, OpenRouter API, asyncpg, Pydantic, structlog  
**Frontend**: React 19, TypeScript, Vite, Tailwind 3, Zustand, Lucide React, Recharts  
**Data**: PostgreSQL (analyses, cache, predictions, traces, metrics), SQLite (portfolio, checkpoints)  
**Deploy**: Fly.io (backend) + Neon (serverless Postgres, Singapore) + Vercel (frontend)  
**CI**: GitHub Actions (ruff, mypy, oxlint, tsc, pytest, Playwright, Semgrep, pip-audit, npm-audit, Docker build)  
**Testing**: pytest + Hypothesis + Playwright + promptfoo (unit, property-based, e2e, LLM eval)

---

## Project Structure

```
backend/
├── src/
│   ├── agent/
│   │   ├── graph.py              # LangGraph DAG definition
│   │   ├── events.py             # Domain SSE event schema + emitter
│   │   ├── debate_schemas.py     # Pydantic models for bull/bear/CIO
│   │   ├── circuit_breaker.py    # Sliding-window circuit breaker
│   │   ├── concurrency.py        # Semaphore-bounded async execution
│   │   ├── nodes/
│   │   │   ├── debate.py         # Adversarial committee (bull→bear→CIO)
│   │   │   ├── fetch_data.py     # Parallel MCP tool calls
│   │   │   └── ...
│   │   └── prompts/              # System/human prompt templates
│   ├── api/
│   │   ├── main.py               # FastAPI app with middleware stack
│   │   └── routes/               # analyze, stream, ops, replay, calibration
│   ├── ops/                      # Metrics collector, trace store, chaos injection
│   ├── cache/                    # PostgreSQL SWR cache + budget guards
│   ├── middleware/               # Auth, rate limit, cost tracking, security headers
│   └── mcp_servers/              # 4 FastMCP tool servers (market, news, portfolio, SEC)
├── tests/                        # pytest (unit, integration, property, chaos, golden)
└── Dockerfile                    # Multi-stage, non-root, healthcheck

frontend/
├── src/
│   ├── stores/analysisStore.ts   # Zustand streaming + debate state
│   ├── hooks/useAnalysisStream.ts # SSE EventSource with reconnection
│   ├── components/
│   │   ├── StreamingAnalysisPage.tsx  # Main streaming experience
│   │   ├── OpsPage.tsx                # Production ops dashboard
│   │   ├── ReplayPage.tsx             # Trace replay viewer
│   │   ├── DebatePanel.tsx            # Live bull/bear/CIO debate
│   │   ├── CalibrationPage.tsx        # Track record + calibration
│   │   └── AnalysisCard/             # Structured analysis display
│   └── types/
└── vitest.config.ts

docs/
├── adr/                          # 7 Architecture Decision Records
├── slo.md                        # Service Level Objectives + error budget
├── ARCHITECTURE.md               # System diagrams, failure modes
├── AI_SECURITY_POSTURE.md        # LLM threat model, trust boundaries
└── RUNBOOK.md                    # Operational playbook

evals/                            # promptfoo LLM evaluation (18+ cases)
tests/e2e/                        # Playwright (5 specs, 3 browsers)
```

---

## Observability

| Signal | Implementation |
|--------|---------------|
| Health checks | `GET /api/health` (liveness), `GET /api/health/ready` (DB + budget + circuit breaker) |
| Metrics | In-memory histograms + Postgres snapshots; exposed via `/api/ops/metrics` |
| Tracing | Full agent traces stored with correlation IDs; replayable via `/replay` |
| SLOs | 7-day rolling availability, p95 latency, error budget burn; visible on `/ops` |
| Logging | Structured JSON with correlation_id, sensitive field redaction, stage timing |
| Alerting | Error budget burn rate thresholds documented in [SLO doc](docs/slo.md) |

---

## Testing

| Layer | Tool | Coverage |
|-------|------|----------|
| Unit + integration | pytest | Schema validation, events, cache, circuit breaker, chaos injection |
| Property-based | Hypothesis | Ticker validation, sentiment bounds, JSON extraction, budget invariants |
| E2E | Playwright | 5 specs across 3 browsers (analysis flow, error states, accessibility) |
| LLM evaluation | promptfoo | 18 cases: structured output, factual grounding, safety, citations, reasoning balance |
| Golden fixtures | pytest | 20 scenarios with mocked tool responses for deterministic testing |
| Security | Semgrep + pip-audit + npm-audit | Custom SAST rules targeting LLM-specific risks |

```bash
cd backend && pytest -q --tb=short
cd frontend && npm run lint && npm run test:run
npx playwright test
```

---

## Security

Custom SAST rules target this stack's actual risks: prompt injection via f-strings, SQL interpolation, missing await on async DB, secrets in logs. Full threat model in [AI Security Posture](docs/AI_SECURITY_POSTURE.md).

CI enforces: Semgrep (custom rules), hadolint (Dockerfile), pip-audit, npm audit. Security exceptions tracked with owner and expiry.

---

## Quick Start

```bash
# One command (starts postgres, backend, frontend)
./scripts/dev.sh

# Or manually:
docker compose up -d postgres
cd backend && pip install -e ".[dev]" && uvicorn src.api.main:app --reload &
cd frontend && npm install && npm run dev
```

Environment variables needed:
```
OPENROUTER_API_KEY    # Required: get free key at openrouter.ai
DATABASE_URL          # PostgreSQL connection string
NEWS_API_KEY          # Optional: NewsAPI.org key
DEMO_PASSWORD         # Optional: gate the demo
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| [Architecture Decision Records](docs/adr/) | 7 decisions with context, rationale, and tradeoffs |
| [Service Level Objectives](docs/slo.md) | Availability, latency, error budget targets and measurement |
| [Architecture](docs/ARCHITECTURE.md) | System diagrams, request lifecycle, failure modes |
| [API Reference](docs/API.md) | Every endpoint with examples and error cases |
| [AI Security Posture](docs/AI_SECURITY_POSTURE.md) | LLM threat model, trust boundaries |
| [Runbook](docs/RUNBOOK.md) | Operational playbook for common failure scenarios |
| [Design System](docs/design-system.md) | Tokens, components, loading/error/empty states |

---

## Known Limitations

- **Not financial advice.** Outputs are for educational/demonstration purposes only.
- **OpenRouter free tier**: 20 req/min. Aggressive caching keeps usage well within limits.
- **No real-time prices**: yfinance data has 15-min delay during market hours.
- **SEC filings**: Only 10-K summaries. No 8-K, no earnings call transcripts.
- **Single retry on validation failure**: If the LLM produces invalid JSON twice, falls back to partial extraction with disclosed data_gaps.
- **Shared demo password**: Production uses a single password gate, not user accounts.

---

<a id="walkthrough"></a>
## Video Walkthrough

<!-- TODO: Record and embed 90s Loom/YouTube walkthrough showing:
  1. Instant pre-cached demo loading
  2. Ops dashboard with live metrics
  3. Chaos mode triggering graceful degradation
  4. Trace replay stepping through a recorded analysis
  5. Live analysis streaming in real-time
-->

*90-second walkthrough coming soon.*

---

*For educational purposes. Not investment advice.*
