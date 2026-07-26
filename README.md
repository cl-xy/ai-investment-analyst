# AI Investment Analyst

[![CI](https://github.com/cl-xy/ai-investment-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/cl-xy/ai-investment-analyst/actions/workflows/ci.yml)

Multi-agent investment analysis system with real-time streaming trace, structured outputs, and source-grounded citations.

[Live Demo](https://ai-investment-analyst.vercel.app) · Demo password: `investor2026`

---

## What it does

Enter a ticker symbol → watch a multi-agent pipeline execute in real-time:

1. **Router** classifies intent and extracts tickers (GPT-OSS 20B, ~100ms)
2. **Fetch Data** calls 5 tools across 4 MCP servers in parallel (market quotes, fundamentals, indicators, news, SEC filings)
3. **Analyze** synthesizes data into a structured assessment with citations (GPT-OSS 120B, JSON mode)
4. **Report** generates a cohesive narrative across all analyzed tickers

Every step streams to the frontend via SSE. You see tool calls resolve, cache hits light up green, and analysis text stream in token by token.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React 19)                       │
│  EventSource → Zustand Store → Trace Panel + Analysis Cards      │
└──────────────────────────────┬──────────────────────────────────┘
                               │ SSE (text/event-stream)
┌──────────────────────────────┴──────────────────────────────────┐
│                      FastAPI Backend                              │
│  ┌─────────┐  ┌───────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ Router  │→ │ Fetch Data│→ │ Analyze  │→ │Generate Report │  │
│  │(20B LLM)│  │(5 MCP     │  │(120B LLM)│  │  (120B LLM)    │  │
│  │         │  │ tools ∥)  │  │JSON mode │  │                │  │
│  └─────────┘  └───────────┘  └──────────┘  └────────────────┘  │
│                      LangGraph StateGraph                        │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────────┘
       │          │          │          │          │
  ┌────┴───┐ ┌───┴────┐ ┌───┴───┐ ┌───┴───┐ ┌───┴──────┐
  │yfinance│ │NewsAPI │ │  SEC  │ │SQLite │ │PostgreSQL│
  │ quotes │ │  + RSS │ │EDGAR  │ │portfolio│ │ analyses │
  └────────┘ └────────┘ └───────┘ └───────┘ │  cache   │
                                             │  runs    │
                                             └──────────┘
```

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Agent orchestration | LangGraph | StateGraph with typed state, conditional edges, checkpointing |
| Tool servers | FastMCP | Protocol-level tool interop, each server independently deployable |
| LLM provider | Groq (free tier) | OpenAI-compatible API, fast inference, JSON mode support |
| Streaming | SSE with domain events | Simpler than WebSocket, works through all proxies, built-in reconnection |
| Structured output | Groq JSON mode + Pydantic | Schema validation with retry, replaces brittle regex parsing |
| Caching | PostgreSQL stale-while-revalidate | Serve stale instantly, refresh in background. Single data store. |
| Frontend state | Zustand | Minimal boilerplate, works naturally with SSE event dispatch |
| Design | Dark-first, CSS custom properties | Tailwind tokens reference CSS vars, theme switch is instant |

## SSE Event Schema

The backend emits domain-specific events (not raw LangGraph internals):

```
run_started      → {tickers}
node_started     → {node_name}
node_completed   → {node_name, duration_ms}
tool_call        → {tool_name, args}
tool_result      → {tool_name, success, cached, duration_ms, source_id}
llm_token        → {text}
analysis_complete → {ticker, analysis}
run_completed    → {total_duration_ms, total_tokens, cost_usd}
heartbeat        → {}  (every 15s)
```

Monotonic sequence IDs enable gapless reconnection via `Last-Event-ID`.

## Structured Analysis Output

Every analysis is validated through Pydantic:

```python
class AnalysisOutput(BaseModel):
    ticker: str
    signal: Literal["buy", "hold", "sell", "insufficient_data"]
    confidence: Literal["high", "medium", "low"]
    sentiment_score: float  # -1.0 to 1.0
    thesis: str
    bull_case: list[str]
    bear_case: list[str]
    risk_flags: list[str]
    citations: list[Citation]  # source_id → claim → provider
    data_gaps: list[str]       # what was unavailable
```

Citations link claims to specific tool results. Data gaps are always disclosed.

## Stack

**Backend**: Python 3.11, FastAPI, LangGraph, FastMCP, Groq API, asyncpg (PostgreSQL), Pydantic  
**Frontend**: React 19, TypeScript, Vite, Tailwind 3, Zustand, Lucide React, Recharts  
**Data**: PostgreSQL (analyses, cache, runs, budget), SQLite (portfolio, checkpoints)  
**Deploy**: Fly.io (backend, containerized) + Neon (serverless PostgreSQL) + Vercel (frontend)  
**CI**: GitHub Actions (lint, type-check, test, docker build)

## Project Structure

```
backend/
├── src/
│   ├── agent/
│   │   ├── graph.py              # LangGraph DAG definition
│   │   ├── events.py             # Domain SSE event schema + emitter
│   │   ├── structured_output.py  # Pydantic schemas for LLM outputs
│   │   ├── circuit_breaker.py    # Sliding-window circuit breaker
│   │   ├── concurrency.py        # Semaphore-bounded async execution
│   │   ├── nodes/                # Graph nodes (router, fetch, analyze, report)
│   │   └── prompts/              # System/human prompt templates
│   ├── api/
│   │   ├── main.py               # FastAPI app entry
│   │   └── routes/               # Endpoints (analyze, stream, health, admin, eval)
│   ├── cache/                    # PostgreSQL SWR cache + budget guards
│   ├── metrics.py                # In-memory counters + histograms (no deps)
│   ├── middleware/               # Auth, rate limiting, cost tracking, security headers
│   └── mcp_servers/              # 4 FastMCP tool servers
├── tests/                        # pytest (unit, integration, property-based, chaos, golden)
│   └── fixtures/                 # 20 golden test scenarios
└── Dockerfile                    # Multi-stage, non-root, healthcheck

frontend/
├── src/
│   ├── stores/analysisStore.ts   # Zustand streaming state
│   ├── hooks/useAnalysisStream.ts # SSE EventSource with reconnection
│   ├── components/
│   │   ├── StreamingAnalysisPage.tsx  # Main streaming experience
│   │   ├── AgentTracePanel.tsx        # Real-time execution trace
│   │   └── AnalysisCard/             # Structured analysis display
│   └── types/                    # TypeScript interfaces
└── vitest.config.ts              # Frontend test config

scripts/
├── dev.sh                        # One-command local startup
├── lint.sh                       # Local quality gates (mirrors CI)
└── security-scan.sh              # Semgrep + pip-audit + npm-audit + secrets

tests/e2e/                        # Playwright (5 specs, 3 browsers)
evals/                            # promptfoo LLM evaluation (18 cases)
docs/                             # Architecture, API, Runbook, Security, ADRs
```

## Security

Custom SAST rules target this stack's real risks (prompt injection via f-strings, SQL interpolation, missing await on async DB, secrets in logs). See [AI Security Posture](docs/AI_SECURITY_POSTURE.md) for the full threat model.

CI enforces: Semgrep (custom rules), hadolint (Dockerfile), pip-audit, npm audit. Security exceptions tracked in `security-exceptions.yaml` with owner and expiry.

## Testing

| Layer | Tool | What it covers |
|-------|------|---------------|
| Unit + integration | pytest | Schema validation, events, cache, circuit breaker, chaos |
| Property-based | Hypothesis | Ticker validation, sentiment bounds, JSON extraction, budget invariants |
| E2E | Playwright | App loads, analysis flow, error states, responsive, accessibility |
| LLM evaluation | promptfoo | 18 cases: structured output, factual grounding, safety, citations, balanced reasoning |
| Golden fixtures | pytest | 20 scenarios with mocked tool responses |

```bash
make test          # backend pytest
make eval-llm      # promptfoo against Groq API
npx playwright test  # E2E (starts frontend automatically)
```

## Observability

- Health: `GET /api/health` (liveness), `GET /api/health/ready` (checks DB, budget, circuit breaker)
- Metrics: `GET /api/metrics` (counters + histograms, analysis latency p50/p95/p99, tool call rates)
- Logging: structured JSON with request_id correlation, sensitive field redaction
- Circuit breaker: auto-trips on consecutive Groq failures, serves cached results while open

## Quick Start (Development)

```bash
./scripts/dev.sh    # one-command: starts postgres, backend, frontend
./scripts/lint.sh   # mirrors CI quality gates
./scripts/security-scan.sh  # semgrep + pip-audit + npm audit + detect-secrets
```

Or manually:
```bash
docker compose up -d postgres
cd backend && uvicorn src.api.main:app --reload &
cd frontend && npm run dev
```

## Documentation

| Document | Purpose |
|----------|---------|
| [Architecture](docs/ARCHITECTURE.md) | System diagrams, request lifecycle, failure modes, concurrency model |
| [API Reference](docs/API.md) | Every endpoint with curl examples and error cases |
| [AI Security Posture](docs/AI_SECURITY_POSTURE.md) | LLM threat model, trust boundaries, mitigations |
| [Runbook](docs/RUNBOOK.md) | Operational playbook: Groq 429s, Neon exhaustion, SSE drops, rollback |
| [Contributing](docs/CONTRIBUTING.md) | Setup, workflow, commit conventions, PR checklist |
| [Security Exceptions](docs/SECURITY_EXCEPTIONS.md) | Acknowledged findings with justification and expiry |
| [Design System](docs/design-system.md) | Tokens, component patterns, loading/error/empty states, accessibility |
| [ADRs](docs/adr/) | 11 architectural decisions with context and tradeoffs |

## Known Limitations

- **Not financial advice.** Outputs are for educational/demonstration purposes only.
- **Groq free tier**: 1K RPM, 250K TPM. Demo uses aggressive caching to stay well within limits.
- **No real-time prices**: yfinance data has 15-min delay during market hours.
- **SEC filings**: Only 10-K summaries. No 8-K, no earnings call transcripts.
- **Single retry on validation failure**: If the LLM produces invalid JSON twice, falls back to partial extraction.
- **No auth beyond demo gate**: Production deployment uses a shared password, not user accounts.
- **Demo mode**: First analysis may take 10-15s if cache is cold. Subsequent requests use warm cache.

---

*For educational purposes. Not investment advice.*
