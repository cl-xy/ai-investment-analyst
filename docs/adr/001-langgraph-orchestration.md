# ADR-001: LangGraph for Agent Orchestration

**Status:** Accepted
**Date:** 2026-07-01
**Deciders:** cl-xy

## Context

I needed an orchestration layer for the multi-agent investment analysis pipeline. The workflow is: Router, Fetch Data, Analyze, Report. Each step has distinct inputs/outputs, and the frontend streams results in real time via SSE.

Candidates considered: LangGraph, AutoGen, CrewAI.

## Decision

Use LangGraph with StateGraph for agent orchestration.

Key reasons:

- StateGraph gives explicit, programmatic control over node transitions. I define exactly which nodes connect and under what conditions, rather than relying on LLM-driven routing between agents.
- `astream_events` v2 provides a native async generator that maps cleanly to SSE. No polling, no websockets, just yield events as the graph executes.
- Built-in checkpoint persistence means I can resume interrupted runs and replay state without rolling my own serialization layer.
- The graph is a DAG I can visualize and test node-by-node. Each node is a plain async function, easy to unit test in isolation.

AutoGen's conversation-based model didn't fit. Agents chatting with each other adds latency and nondeterminism that a structured pipeline doesn't need. CrewAI abstracts too much away, making it hard to control transition logic or stream intermediate state.

## Consequences

**Easier:**
- Adding new pipeline stages is just adding a node and an edge.
- Streaming works out of the box with the event system.
- Testing is straightforward since each node is an isolated function.
- Checkpoint/resume comes free for long-running analyses.

**Harder:**
- LangGraph has a learning curve around state schemas and conditional edges.
- Debugging graph execution requires understanding the event stream format.
- Tightly coupled to LangChain ecosystem for updates and breaking changes.
