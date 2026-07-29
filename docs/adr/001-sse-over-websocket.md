# ADR-001: SSE Over WebSocket for Streaming

**Status:** Accepted  
**Date:** 2025-03-15

## Context

The multi-agent analysis pipeline (Router, Fetch Data, Debate, Peer Compare, Report) takes 60-120 seconds to complete. Users need real-time progress feedback as the agent moves through each node. The frontend needs to display which step is active, show intermediate results (bull/bear arguments as they arrive), and surface errors without polling.

Two viable transport options: Server-Sent Events (SSE) or WebSocket.

## Decision

Use SSE with a domain-specific event schema. Events are mapped through an adapter layer before reaching the client. Raw LangGraph internal events never leak to the frontend.

The SSE endpoint emits typed events (`analysis_started`, `node_entered`, `ticker_analysis_complete`, `debate_update`, `analysis_complete`, `error`) with structured JSON payloads validated by Pydantic schemas.

## Reasons

- **Unidirectional fits the use case.** Analysis runs are fire-and-forget. The client submits a ticker, then only receives progress. No need for bidirectional messaging.
- **Works through Fly.io and Vercel proxies.** SSE uses standard HTTP/1.1 chunked responses. No upgrade negotiation, no sticky sessions required. WebSocket on Fly.io needs specific configuration and connection draining.
- **Built-in browser reconnection.** `EventSource` handles reconnects with `Last-Event-ID` automatically. WebSocket reconnection requires custom logic with exponential backoff.
- **Simpler server implementation.** FastAPI's `StreamingResponse` with `text/event-stream` content type. No connection registry, no ping/pong frames, no state sync.
- **15s heartbeat keeps proxies happy.** A simple `: keepalive\n\n` comment line prevents intermediate proxies from closing idle connections during long LLM calls (30-40s each for reasoning models).

## Consequences

**Positive:**
- Zero WebSocket infrastructure complexity (no upgrade handling, no connection pools)
- Frontend uses native `EventSource` API with minimal wrapper code
- Proxy-friendly: works behind Cloudflare, Vercel, Fly.io without special config
- `X-Accel-Buffering: no` + `Cache-Control: no-cache` headers prevent buffering

**Negative:**
- No bidirectional communication. If we ever need mid-analysis cancellation, we'd need a separate REST endpoint (acceptable tradeoff).
- SSE has a browser limit of ~6 concurrent connections per domain (HTTP/1.1). Not an issue since users run one analysis at a time.
- Reconnection starts a new analysis (no resume from checkpoint mid-stream). This wastes rate limit tokens but is acceptable for the current use case.
