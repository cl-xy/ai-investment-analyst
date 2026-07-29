# API Reference

Base URL: `https://ai-investment-analyst.fly.dev/api` (production) or `http://localhost:8000/api` (development)

## Authentication

### Demo Auth Middleware

In production, analysis endpoints are protected by a shared demo password (set via `DEMO_PASSWORD` env var). When configured:

- **Protected endpoints**: all paths starting with `/api/analyze`
- **Public endpoints**: `/api/health`, `/api/explore`, `/api/dashboard`, `/api/admin`

Provide credentials via either:
- Query parameter: `?password=<demo_password>`
- Header: `X-Demo-Password: <demo_password>`

When `DEMO_PASSWORD` is not set (local development), the auth gate is disabled entirely.

### Scheduler Token

Admin and scheduled endpoints use a separate `SCHEDULER_SECRET_TOKEN` for machine-to-machine auth. Provided via:
- `Authorization: Bearer <token>` (admin endpoints)
- `X-Scheduler-Token: <token>` (scheduled endpoints)

### Rate Limiting

Per-IP rate limiting via slowapi: **10 requests/minute** on analysis endpoints. Returns HTTP 429 when exceeded.

Upstream OpenRouter free tier limits: 20 req/min. The circuit breaker activates after 5 consecutive LLM failures within 60 seconds, with a 30-second cooldown before probing again.

---

## Endpoints

### Health

#### GET /api/health

Basic liveness probe.

**Response** `200 OK`

```json
{"status": "ok"}
```

```bash
curl http://localhost:8000/api/health
```

#### GET /api/health/ready

Readiness probe with database connectivity check.

**Response** `200 OK`

```json
{"status": "ok", "database": "connected"}
```

**Response** `503 Service Unavailable`

```json
{"status": "unhealthy", "database": "unreachable"}
```

```bash
curl http://localhost:8000/api/health/ready
```

---

### Analysis

#### POST /api/analyze

Run a synchronous analysis for one or more tickers. Returns structured results persisted to PostgreSQL.

**Request Body**

```json
{
  "tickers": ["NVDA", "AAPL"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tickers` | `string[]` | Yes | Ticker symbols (min 1) |

**Response** `200 OK`

```json
{
  "id": "a1b2c3d4-...",
  "tickers": ["NVDA", "AAPL"],
  "report_markdown": "## Investment Analysis Report\n\n...",
  "analyses": {
    "NVDA": {
      "ticker": "NVDA",
      "signal": "buy",
      "confidence": "high",
      "sentiment_score": 0.82,
      "news_summary": "Strong AI chip demand continues...",
      "risk_flags": ["High valuation relative to sector"],
      "price_data": {"price": 135.50, "change_pct": 2.1, "volume": 45000000},
      "fundamentals": {"pe_ratio": 65.2, "market_cap": 3300000000000},
      "sec_notes": "10-K highlights accelerating data center revenue..."
    }
  },
  "created_at": "2026-07-26T10:30:00Z"
}
```

**Errors**

| Status | Condition |
|--------|-----------|
| 400 | Empty tickers list |
| 401 | Demo password required (production) |
| 500 | Analysis pipeline failure |

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["NVDA"]}'
```

---

#### GET /api/analyze/stream

SSE streaming endpoint for real-time analysis with full agent trace. This is the primary endpoint for the frontend.

**Query Parameters**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `tickers` | `string` | Yes | Comma-separated ticker symbols |

**Validation Rules**
- Each ticker must match `[A-Z0-9.]{1,10}`
- Maximum 5 tickers per request
- At least 1 ticker required

**Response** `200 OK` (Content-Type: `text/event-stream`)

The response is an SSE stream. Each message has three fields:

```
id: <seq>
event: <event_type>
data: <json_envelope>

```

**Event Stream Example**

```
id: 1
event: run_started
data: {"run_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","seq":1,"type":"run_started","timestamp":"2026-07-26T10:30:00.123Z","node":null,"tool":null,"payload":{"tickers":["NVDA"]}}

id: 2
event: node_started
data: {"run_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","seq":2,"type":"node_started","timestamp":"2026-07-26T10:30:00.456Z","node":"router","tool":null,"payload":{"node_name":"router"}}

id: 3
event: node_completed
data: {"run_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","seq":3,"type":"node_completed","timestamp":"2026-07-26T10:30:01.100Z","node":"router","tool":null,"payload":{"node_name":"router","duration_ms":644}}

id: 4
event: node_started
data: {"run_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","seq":4,"type":"node_started","timestamp":"2026-07-26T10:30:01.102Z","node":"fetch_data","tool":null,"payload":{"node_name":"fetch_data"}}

id: 5
event: tool_call
data: {"run_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","seq":5,"type":"tool_call","timestamp":"2026-07-26T10:30:01.105Z","node":"fetch_data","tool":"get_quote","payload":{"tool_name":"get_quote","args":{"ticker":"NVDA"}}}

id: 6
event: tool_result
data: {"run_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","seq":6,"type":"tool_result","timestamp":"2026-07-26T10:30:01.350Z","node":"fetch_data","tool":"get_quote","payload":{"tool_name":"get_quote","success":true,"cached":false,"duration_ms":245,"source_id":"get_quote:1722000000"}}

id: 12
event: analysis_complete
data: {"run_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","seq":12,"type":"analysis_complete","timestamp":"2026-07-26T10:30:15.200Z","node":null,"tool":null,"payload":{"ticker":"NVDA","analysis":{"ticker":"NVDA","signal":"buy","confidence":"high","sentiment_score":0.82,"news_summary":"...","risk_flags":["..."],"price_data":{...},"fundamentals":{...},"sec_notes":"..."}}}

id: 13
event: run_completed
data: {"run_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","seq":13,"type":"run_completed","timestamp":"2026-07-26T10:30:15.500Z","node":null,"tool":null,"payload":{"tickers":["NVDA"],"total_duration_ms":15377,"total_tokens":8420,"cost_usd":0.0}}

```

**Event Types**

| Event | Description |
|-------|-------------|
| `run_started` | Stream opened, analysis beginning |
| `node_started` | LangGraph node activated |
| `node_completed` | LangGraph node finished (includes `duration_ms`) |
| `tool_call` | MCP tool invocation started |
| `tool_result` | MCP tool returned (success/failure, duration, cache status) |
| `llm_token` | Streaming text token from LLM |
| `citation` | Source citation emitted |
| `analysis_complete` | Full structured analysis for one ticker |
| `warning` | Non-fatal issue (e.g., data gap) |
| `error` | Fatal or recoverable error |
| `run_completed` | All analysis finished (total metrics) |
| `heartbeat` | Keepalive every 15 seconds |

**Connection Behavior**
- Heartbeat every 15 seconds (prevents proxy buffering)
- 120-second execution timeout (emits error event, then closes)
- `id` field enables `Last-Event-ID` reconnection
- `X-Accel-Buffering: no` header disables nginx buffering

**Errors** (returned as JSON, not SSE)

| Status | Condition |
|--------|-----------|
| 200 + error JSON | Invalid ticker format, too many tickers, empty input |
| 401 | Demo password required (production) |

```bash
curl -N "http://localhost:8000/api/analyze/stream?tickers=NVDA,AAPL"
```

---

### Compare

#### GET /api/compare

Compare 2-3 tickers. Runs analysis if needed (uses cache when available), then returns comparative results.

**Query Parameters**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `tickers` | `string` | Yes | Comma-separated tickers (2-3) |

**Response** `200 OK`

```json
{
  "tickers": ["NVDA", "AMD"],
  "analyses": {
    "NVDA": {
      "ticker": "NVDA",
      "signal": "buy",
      "confidence": "high",
      "sentiment_score": 0.82,
      "news_summary": "...",
      "risk_flags": [],
      "price_data": {},
      "fundamentals": {},
      "sec_notes": ""
    },
    "AMD": {
      "ticker": "AMD",
      "signal": "hold",
      "confidence": "medium",
      "sentiment_score": 0.55,
      "news_summary": "...",
      "risk_flags": ["Competitive pressure from NVDA"],
      "price_data": {},
      "fundamentals": {},
      "sec_notes": ""
    }
  },
  "report_markdown": "## Comparative Analysis\n\n..."
}
```

**Errors**

| Status | Condition |
|--------|-----------|
| 400 | Fewer than 2 tickers |
| 400 | More than 3 tickers |

```bash
curl "http://localhost:8000/api/compare?tickers=NVDA,AMD"
```

---

### Dashboard

#### GET /api/dashboard

List all persisted analyses, ordered by most recent first.

**Response** `200 OK`

```json
[
  {
    "id": "a1b2c3d4-...",
    "tickers": ["NVDA", "AAPL"],
    "created_at": "2026-07-26T10:30:00Z"
  },
  {
    "id": "e5f6g7h8-...",
    "tickers": ["TSLA"],
    "created_at": "2026-07-25T14:00:00Z"
  }
]
```

```bash
curl http://localhost:8000/api/dashboard
```

#### GET /api/dashboard/{analysis_id}

Retrieve a specific persisted analysis with full ticker details.

**Path Parameters**

| Param | Type | Description |
|-------|------|-------------|
| `analysis_id` | `uuid` | Analysis UUID |

**Response** `200 OK`

Same schema as `POST /api/analyze` response.

**Errors**

| Status | Condition |
|--------|-----------|
| 400 | Invalid UUID format |
| 404 | Analysis not found |

```bash
curl http://localhost:8000/api/dashboard/a1b2c3d4-5678-90ab-cdef-1234567890ab
```

#### DELETE /api/dashboard/{analysis_id}

Delete a persisted analysis and its ticker records (cascade).

**Response** `204 No Content`

**Errors**

| Status | Condition |
|--------|-----------|
| 400 | Invalid UUID format |
| 404 | Analysis not found |

```bash
curl -X DELETE http://localhost:8000/api/dashboard/a1b2c3d4-5678-90ab-cdef-1234567890ab
```

---

### Explore

#### GET /api/explore

Returns top 20 trending US stocks from Yahoo Finance. Results are cached in-memory for 5 minutes.

**Response** `200 OK`

```json
{
  "stocks": [
    {
      "rank": 1,
      "ticker": "NVDA",
      "name": "NVIDIA Corporation",
      "price": 135.50,
      "change_pct": 2.14,
      "volume": 45000000
    },
    {
      "rank": 2,
      "ticker": "TSLA",
      "name": "Tesla, Inc.",
      "price": 248.30,
      "change_pct": -1.05,
      "volume": 32000000
    }
  ],
  "updated_at": "2026-07-26T10:30:00Z"
}
```

**Errors**

| Status | Condition |
|--------|-----------|
| 502 | Yahoo Finance unavailable or returned no data |

```bash
curl http://localhost:8000/api/explore
```

#### GET /api/explore/{ticker}/detail

Detailed stock information: 30-day price history, company description, industry, and recent news headlines. Results cached for 15 minutes per ticker.

**Path Parameters**

| Param | Type | Description |
|-------|------|-------------|
| `ticker` | `string` | Stock ticker symbol |

**Response** `200 OK`

```json
{
  "ticker": "NVDA",
  "industry": "Semiconductors",
  "description": "NVIDIA Corporation provides graphics and compute solutions...",
  "price_history": [
    {"date": "2026-06-26", "close": 128.40},
    {"date": "2026-06-27", "close": 130.15},
    {"date": "2026-07-25", "close": 134.80},
    {"date": "2026-07-26", "close": 135.50}
  ],
  "trending_reason": [
    {"title": "NVIDIA Announces Next-Gen AI Chip Architecture", "url": "https://..."},
    {"title": "Data Center Revenue Exceeds Expectations", "url": "https://..."}
  ]
}
```

```bash
curl http://localhost:8000/api/explore/NVDA/detail
```

---

### Admin

All admin endpoints require the `SCHEDULER_SECRET_TOKEN` via `Authorization: Bearer <token>` header.

#### POST /api/admin/warm-cache

Pre-warm cache for demo tickers. Designed to be called by a GitHub Actions nightly cron job.

**Response** `200 OK`

```json
{
  "status": "ok",
  "tickers": ["AAPL", "NVDA", "TSLA", "MSFT", "GOOGL", "AMZN", "META", "SPY"],
  "message": "Cache warming initiated for 8 tickers"
}
```

**Errors**

| Status | Condition |
|--------|-----------|
| 401 | Missing or malformed Bearer token |
| 403 | Invalid token |
| 503 | Scheduler token not configured on server |

```bash
curl -X POST http://localhost:8000/api/admin/warm-cache \
  -H "Authorization: Bearer $SCHEDULER_SECRET_TOKEN"
```

#### GET /api/admin/budget

Return current API budget usage for all tracked providers (OpenRouter, NewsAPI, etc.).

**Response** `200 OK`

```json
{
  "status": "ok",
  "budgets": {
    "openrouter": {"used": 450, "limit": 1000, "window": "hourly"},
    "newsapi": {"used": 80, "limit": 100, "window": "daily"}
  }
}
```

```bash
curl http://localhost:8000/api/admin/budget \
  -H "Authorization: Bearer $SCHEDULER_SECRET_TOKEN"
```

#### GET /api/admin/health/detailed

Extended health check with version info. Public (no auth required).

**Response** `200 OK`

```json
{
  "status": "healthy",
  "version": "0.2.0",
  "demo_tickers": ["AAPL", "NVDA", "TSLA", "MSFT", "GOOGL", "AMZN", "META", "SPY"]
}
```

```bash
curl http://localhost:8000/api/admin/health/detailed
```

---

### Scheduled

#### POST /api/scheduled/refresh-portfolio

Trigger a fresh analysis for all tickers in the user's portfolio. Used by scheduled jobs to keep analyses current.

**Headers**

| Header | Required | Description |
|--------|----------|-------------|
| `X-Scheduler-Token` | Yes | Scheduler secret token |

**Behavior**
- Acquires a run lock (prevents concurrent refreshes)
- Skips if a refresh ran within the last 900 seconds (configurable)
- Skips if portfolio is empty
- Runs `analyze_tickers` with `force_refresh=True`

**Response** `200 OK` (success)

```json
{
  "status": "success",
  "message": "Portfolio analysis refreshed",
  "tickers": ["NVDA", "AAPL", "TSLA"],
  "analysis_id": "a1b2c3d4-...",
  "created_at": "2026-07-26T10:30:00Z",
  "duration_ms": 45200
}
```

**Response** `200 OK` (skipped)

```json
{
  "status": "skipped",
  "message": "Refresh is already running",
  "tickers": [],
  "analysis_id": null,
  "created_at": "2026-07-26T10:30:00Z",
  "duration_ms": 2
}
```

**Errors**

| Status | Condition |
|--------|-----------|
| 401 | Missing or invalid scheduler token |
| 503 | Scheduler token not configured |

```bash
curl -X POST http://localhost:8000/api/scheduled/refresh-portfolio \
  -H "X-Scheduler-Token: $SCHEDULER_SECRET_TOKEN"
```

---

### Evaluation

#### GET /api/eval/summary

Aggregated eval metrics from the last 100 runs. Used by the eval dashboard.

**Response** `200 OK`

```json
{
  "total_runs": 87,
  "schema_validation_rate": 94.3,
  "avg_latency_ms": 12400,
  "p95_latency_ms": 28500,
  "citation_coverage": 3.2,
  "tool_success_rate": 96.5,
  "cache_hit_rate": 42.0,
  "last_run_at": "2026-07-26T10:30:00Z"
}
```

```bash
curl http://localhost:8000/api/eval/summary
```

#### GET /api/eval/history

Daily aggregated metrics for the last 30 days.

**Response** `200 OK`

```json
{
  "days": [
    {
      "date": "2026-07-25",
      "runs": 12,
      "avg_latency_ms": 11800,
      "schema_validation_rate": 91.7,
      "total_tokens": 95000
    },
    {
      "date": "2026-07-26",
      "runs": 8,
      "avg_latency_ms": 13200,
      "schema_validation_rate": 100.0,
      "total_tokens": 67000
    }
  ]
}
```

```bash
curl http://localhost:8000/api/eval/history
```

---

## Response Schema Reference

### TickerAnalysis

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | `string` | Ticker symbol |
| `signal` | `"buy" \| "hold" \| "sell" \| "insufficient_data"` | Investment signal |
| `confidence` | `"high" \| "medium" \| "low"` | Confidence level |
| `sentiment_score` | `float` | Sentiment score (-1.0 to 1.0) |
| `news_summary` | `string` | Prose summary of news sentiment |
| `risk_flags` | `string[]` | Identified risk factors |
| `price_data` | `object` | Price, change, volume data |
| `fundamentals` | `object` | P/E, market cap, etc. |
| `sec_notes` | `string` | Summary of SEC filing highlights |

### AnalyzeResponse

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string (uuid)` | Persisted analysis ID |
| `tickers` | `string[]` | Analyzed tickers |
| `report_markdown` | `string` | Narrative report in Markdown |
| `analyses` | `dict[string, TickerAnalysis]` | Per-ticker structured analyses |
| `created_at` | `string (ISO 8601)` | Creation timestamp |

---

## Error Format

All error responses follow this structure:

```json
{"detail": "Human-readable error message"}
```

Standard HTTP status codes are used. The API never exposes raw stack traces or internal exception details.

---

## CORS

Allowed origins (configurable via `FRONTEND_URL`):
- `http://localhost:5173` (Vite dev server)
- `http://127.0.0.1:5173`
- Production frontend URL

All methods and headers are allowed. Credentials are supported.
