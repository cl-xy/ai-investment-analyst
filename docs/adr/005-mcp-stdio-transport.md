# ADR-005: MCP Tool Servers via stdio Transport

**Status:** Accepted
**Date:** 2026-07-09
**Deciders:** cl-xy

## Context

The system needs to fetch data from four external sources: market data, news, portfolio holdings, and SEC filings. Each source has its own API patterns, authentication, rate limits, and failure modes.

I wanted isolation between these concerns so that a failure in one data source doesn't cascade to others, and each can be developed and tested independently.

## Decision

Implement each data source as a separate MCP (Model Context Protocol) tool server using FastMCP, communicating via stdio transport.

The four servers:
- `market` - stock prices, charts, fundamentals
- `news` - financial news and sentiment
- `portfolio` - user holdings and allocations
- `sec` - SEC filings (10-K, 10-Q, 8-K)

Reasons:

- Process isolation means a crash in the news server doesn't take down market data fetching.
- FastMCP handles the MCP protocol negotiation, tool registration, and JSON-RPC framing. I just write the tool functions.
- Each server can be run standalone for integration testing against its upstream API.
- stdio transport is simple: no ports to manage, no network configuration, no TLS between local processes.
- Adding a new data source means adding a new server, not modifying existing ones.

## Consequences

**Easier:**
- Independent development and testing per data source.
- Fault isolation between data sources.
- Clean separation of concerns.
- FastMCP reduces protocol boilerplate to near zero.

**Harder:**
- Subprocess lifecycle management (start, health check, restart on crash).
- Debugging requires attaching to the right subprocess.
- stdio transport means you can't easily inspect the wire protocol without logging.
- Memory overhead of multiple Python processes (mitigated: each server is lightweight).
