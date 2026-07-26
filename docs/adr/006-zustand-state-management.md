# ADR-006: Zustand for State Management

**Status:** Accepted
**Date:** 2026-07-12
**Deciders:** cl-xy

## Context

The frontend needs to accumulate SSE events into a coherent analysis state: streaming text chunks, trace events, status transitions, error handling. This state drives the entire UI during an analysis run.

Redux is the obvious choice for complex state, but the boilerplate (actions, reducers, selectors, middleware) is heavy for what's fundamentally an event accumulator. MobX adds observable magic that complicates debugging.

## Decision

Use Zustand with a single store for analysis stream state.

Reasons:

- Minimal boilerplate. A Zustand store is a function that returns state and actions. No action types, no reducers, no switch statements.
- The single-store pattern matches the streaming use case perfectly: one object that grows as events arrive.
- No Provider wrapper needed. With React 19, this means cleaner component trees and no context nesting.
- Zustand's `subscribe` API integrates cleanly with EventSource. The SSE handler calls store actions directly.
- Selectors are just functions, making it easy to derive computed state (e.g., "is analysis complete?" from the event history).
- DevTools integration via the devtools middleware for debugging state transitions.

## Consequences

**Easier:**
- Adding new state fields is trivial (just add to the store).
- SSE event handlers are clean: `useAnalysisStore.getState().addEvent(event)`.
- No provider hierarchy to manage.
- Bundle size is tiny (~1KB gzipped).

**Harder:**
- Less structure means less guardrails. Easy to put too much in one store.
- No built-in middleware ecosystem like Redux (but we don't need it).
- Team members familiar with Redux need to adjust to the different mental model.
