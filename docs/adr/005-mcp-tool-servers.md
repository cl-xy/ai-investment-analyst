# ADR-005: FastMCP Tool Server Architecture

**Status:** Accepted  
**Date:** 2025-03-12

## Context

The agent needs structured access to 4+ external data sources, each with different reliability profiles, rate limits, and response schemas:

- **Market data** (yfinance): unlimited but occasionally returns None fields
- **News** (NewsAPI + RSS feeds): 100/day free tier, needs fallback
- **Portfolio** (SQLite): local, always available
- **SEC filings** (EDGAR): 10 req/sec, responses are large, should cache permanently

Direct function calls would work, but coupling the agent to specific data source implementations makes testing difficult and error isolation impossible. A single failing source (SEC EDGAR timeout) shouldn't crash the entire analysis.

## Decision

Use 4 in-process FastMCP tool servers: `market_server`, `news_server`, `portfolio_server`, `sec_server`. Each exposes typed tool functions with schema validation at the boundary. Tools are registered with the agent via LangGraph's tool binding mechanism.

The agent graph (`backend/src/agent/graph.py`) receives MCP tools as a dictionary and binds them into nodes via `functools.partial`. Each tool call is wrapped in try/except at the node level, with failures populating a `data_gaps` field rather than raising.

## Reasons

- **Per-tool error isolation.** A yfinance timeout doesn't affect news fetching. Each tool call is independently wrapped. Failures populate `data_gaps` in the analysis state, and downstream nodes (debate, report) adapt their output based on what data is available.
- **Schema validation at boundaries.** Tool inputs and outputs are typed. Invalid ticker formats are rejected before hitting external APIs. Response shapes are validated before entering the agent state.
- **Standard protocol.** MCP (Model Context Protocol) is a standardized tool interface. The same servers could run as separate processes or be consumed by other agents in the future.
- **Testability.** Tools can be mocked individually in tests. The golden ticker fixture system provides deterministic responses for eval without hitting real APIs.
- **Cache integration.** Each tool call passes through the cache manager (`backend/src/cache/manager.py`) with source-specific TTLs. The tool server doesn't need to know about caching; it's handled at the infrastructure layer.

## Consequences

**Positive:**
- Agent continues producing useful analysis even when 1-2 data sources are down
- `data_gaps` field in reports tells users exactly what information was unavailable
- Adding a new data source means adding a new server without touching existing code
- Tests run without network access using fixture data

**Negative:**
- Slight overhead vs direct function calls (MCP protocol serialization/deserialization). Negligible compared to LLM call latency.
- In-process means a truly broken server (unhandled exception in import) could still affect the process. Mitigated by lazy loading and import-time error handling.
- 4 servers sharing one process means no independent scaling. Acceptable for current load profile.
