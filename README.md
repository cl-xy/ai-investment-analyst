# AI Investment Analyst

[![CI](https://github.com/cl-xy/ai-investment-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/cl-xy/ai-investment-analyst/actions/workflows/ci.yml)

Multi-agent investment analysis system with real-time streaming trace, structured outputs, and source-grounded citations.

[Live Demo](https://ai-investment-analyst.vercel.app) · [Video Walkthrough](#demo-video)

---

## What it does

Enter a ticker symbol → watch a multi-agent pipeline execute in real-time:

1. **Router** classifies intent and extracts tickers (Llama 3.1 8B, ~120ms)
2. **Fetch Data** calls 5 MCP tool servers in parallel (market, fundamentals, indicators, news, SEC filings)
3. **Analyze** synthesizes data into a structured assessment with citations (Llama 3.3 70B, JSON mode)
4. **Report** generates a cohesive narrative across all analyzed tickers

Every step streams to the frontend via SSE — you see tool calls resolve, cache hits light up green, and analysis text stream in token by token.

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
│  │(8B LLM) │  │(5 MCP     │  │(70B LLM) │  │  (70B LLM)     │  │
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
| Design | Dark-first, CSS custom properties | Tailwind tokens reference CSS vars — theme switch is instant |

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
**Deploy**: Railway (backend + Postgres) + Vercel (frontend)  
**CI**: GitHub Actions (lint, type-check, test, docker build)

## Local Setup

```bash
# Clone
git clone https://github.com/cl-xy/ai-investment-analyst.git
cd ai-investment-analyst

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env  # fill in GROQ_API_KEY at minimum

# Frontend
cd ../frontend
npm install

# Run (with local Postgres)
docker compose up -d postgres
cd backend && uvicorn src.api.main:app --reload &
cd frontend && npm run dev
```

Or with Docker:
```bash
cp .env.example .env  # fill in API keys
docker compose up
```

## Project Structure

```
backend/
├── src/
│   ├── agent/
│   │   ├── graph.py              # LangGraph DAG definition
│   │   ├── events.py             # Domain SSE event schema + emitter
│   │   ├── structured_output.py  # Pydantic schemas for LLM outputs
│   │   ├── nodes/                # Graph nodes (router, fetch, analyze, report)
│   │   └── prompts/              # System/human prompt templates
│   ├── api/
│   │   ├── main.py               # FastAPI app entry
│   │   └── routes/               # Endpoints (analyze, stream, admin, health)
│   ├── cache/                    # PostgreSQL SWR cache + budget guards
│   ├── middleware/               # Auth gate + rate limiting + cost tracking
│   └── mcp_servers/              # 4 FastMCP tool servers
├── tests/                        # pytest (events, schemas, cache, nodes)
└── Dockerfile                    # Multi-stage, non-root, healthcheck

frontend/
├── src/
│   ├── stores/analysisStore.ts   # Zustand streaming state
│   ├── hooks/useAnalysisStream.ts # SSE EventSource with reconnection
│   ├── components/
│   │   ├── StreamingAnalysisPage.tsx  # Main streaming experience
│   │   ├── AgentTracePanel.tsx        # Real-time execution trace
│   │   └── TraceEvent.tsx             # Individual trace timeline rows
│   └── styles/                   # CSS custom properties (design tokens)
└── index.html                    # Dark theme default
```

## Known Limitations

- **Not financial advice.** Outputs are for educational/demonstration purposes only.
- **Groq free tier**: 30 req/min, 14,400 req/day. Demo uses aggressive caching.
- **No real-time prices**: yfinance data has 15-min delay during market hours.
- **SEC filings**: Only 10-K summaries. No 8-K, no earnings call transcripts.
- **Single retry on validation failure**: If the LLM produces invalid JSON twice, falls back to partial extraction.
- **No auth beyond demo gate**: Production deployment uses a shared password, not user accounts.

## Eval Methodology

Automated evaluation on a golden test set (20 scenarios):
- Schema validation pass rate (target >95%)
- Citation coverage (% of claims with valid source reference)
- Tool success rate per provider
- Latency p50/p95
- Error recovery rate (partial failures → still produces output)

LLM-as-judge scores output quality on citation support, balanced reasoning, and risk disclosure. Clearly labeled as quality assessment — never claims prediction accuracy.

---

*For educational purposes. Not investment advice.*
