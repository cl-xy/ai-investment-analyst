# ADR-004: Domain Event Abstraction Over Raw LangGraph Events

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** cl-xy

## Context

LangGraph's `astream_events` emits low-level events: `on_chain_start`, `on_llm_stream`, `on_tool_end`, etc. These are implementation details of the graph execution engine. Exposing them directly to the frontend creates tight coupling between the UI and the agent internals.

If I refactor the graph (rename a node, split a step, add retry logic), every frontend consumer breaks.

## Decision

Define a domain-specific event schema that the backend translates LangGraph events into before sending over SSE.

The event types map to user-meaningful stages: `analysis.started`, `data.fetched`, `insight.generated`, `report.chunk`, `analysis.completed`, `analysis.error`. Each event carries a monotonic sequence ID.

Reasons:

- The frontend subscribes to business concepts, not graph internals. Renaming a LangGraph node doesn't break the client.
- Sequence IDs enable reconnection. If the SSE connection drops, the client sends `Last-Event-ID` and resumes from where it left off.
- Typed event schemas (validated with Pydantic on the backend, TypeScript interfaces on the frontend) catch contract drift at build time.
- A heartbeat event (`:ping`) every 15 seconds prevents reverse proxies and load balancers from closing idle connections.

## Consequences

**Easier:**
- Frontend is decoupled from agent implementation details.
- Reconnection is reliable via sequence IDs.
- Contract changes surface as type errors, not runtime bugs.
- Proxy/CDN compatibility via heartbeat.
- Can log/replay event streams for debugging.

**Harder:**
- Translation layer adds code to maintain.
- New graph features require mapping to domain events (or they're invisible to the frontend).
- Sequence ID tracking adds state to the SSE endpoint.
