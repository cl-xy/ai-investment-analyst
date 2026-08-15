# ADR-006: Structured Output Validation (JSON Mode + Pydantic)

**Status:** Accepted  
**Date:** 2025-03-25

## Context

Every LLM call in the pipeline produces structured data: router intent classification, bull/bear debate arguments, CIO verdicts, and final reports. These outputs feed directly into downstream agent nodes, the cache layer, and the frontend via SSE events.

LLMs are unreliable format producers. Common failure modes: wrapping JSON in markdown code fences, truncating output (missing closing braces), inventing fields not in the schema, omitting required fields, and inconsistent nested structures.

Previous approach (prompt-only formatting instructions) failed ~15% of the time in testing, causing silent data corruption or parse errors that surfaced as cryptic frontend bugs.

## Decision

Three-layer validation strategy:

1. **OpenRouter JSON mode** (`response_format={"type": "json_object"}`): forces the model to output valid JSON. Eliminates markdown wrapping and most structural issues.
2. **Pydantic validation**: every LLM response is parsed through a typed schema (`BullCaseOutput`, `BearCaseOutput`, `ModeratorOutput`, `TickerAnalysis`). Catches missing fields, wrong types, invalid enum values.
3. **One retry on validation failure**: if Pydantic raises `ValidationError`, the call is retried once with the error message appended to the prompt. If retry also fails, fall back to `extract_json()` regex as a last resort.

All schemas live in `backend/src/agent/debate_schemas.py` and `backend/src/agent/state.py`. The `max_tokens` parameter is always set explicitly (8192 for debate steps) to prevent silent truncation.

## Reasons

- **JSON mode eliminates the most common failure class.** No more regex-stripping markdown fences or hunting for JSON boundaries in prose output.
- **Pydantic catches what JSON mode misses.** Valid JSON isn't necessarily valid data. A confidence score of "high" instead of 0.85 breaks downstream aggregation. Pydantic enforces the contract.
- **One retry is cost-effective.** Most validation failures are transient (model slightly misformatted one field). A single retry with the error message usually fixes it. More retries waste rate budget.
- **`extract_json()` as last resort, not primary.** Regex extraction is fragile (can match nested JSON incorrectly). It only runs if JSON mode + retry both fail. This happens <1% of the time in production.
- **Explicit `max_tokens` prevents silent truncation.** Without it, the model may stop mid-JSON. The response looks like a failure but is actually just cut off. Setting 8192 gives plenty of room for debate arguments.

## Consequences

**Positive:**
- Parse failure rate dropped from ~15% to <1% after implementing this stack
- Downstream nodes can trust the shape of data they receive
- Validation errors are logged with context (which field, what value) for debugging
- Frontend never receives malformed analysis data via SSE

**Negative:**
- Extra token usage on retry (~2% of requests need it). Acceptable cost for data integrity.
- JSON mode slightly constrains model creativity (no prose preambles). Not an issue since we want structured data, not creative writing.
- `max_tokens=8192` is generous and occasionally produces verbose outputs. Could tune per-step, but consistency is simpler to maintain.
