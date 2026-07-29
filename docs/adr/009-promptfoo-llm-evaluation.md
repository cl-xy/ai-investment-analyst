# ADR-009: promptfoo for LLM Behavior Regression Testing

**Status:** Accepted
**Date:** 2026-07-27
**Deciders:** cl-xy

## Context

LLM outputs are nondeterministic. When I change a prompt template, model version, or system instruction, I need confidence that:

1. Structured output still conforms to the Pydantic schema
2. Analysis is factually grounded in the provided market data (no hallucinated numbers)
3. Safety guardrails still fire (refuses to provide financial advice, flags when data is stale)
4. Citations reference real source_ids from the tool results
5. Reasoning covers bull and bear cases (not one-sided)

Manual spot-checking doesn't scale. I need automated evaluation that runs on demand.

## Decision

Use promptfoo with a suite of 20 eval cases covering five dimensions:

| Dimension | Cases | Assertion type |
|-----------|-------|----------------|
| Structured output compliance | 4 | JSON schema validation, required fields present |
| Factual grounding | 5 | LLM-as-judge: does the output contradict provided data? |
| Safety and refusal | 4 | Contains refusal language, no direct buy/sell advice |
| Citation quality | 3 | All cited source_ids exist in tool results |
| Balanced reasoning | 4 | LLM-as-judge: covers both bull and bear arguments |

Configuration lives in `evals/promptfooconfig.yaml`. Test cases in `evals/cases/`.

Runs as a manual-dispatch GitHub Actions workflow (`workflow_dispatch`), not on every PR. Reasons:
- API costs add up across 20 cases with multiple providers
- Nondeterminism means occasional false failures that would block PRs
- Prompt changes are infrequent enough that manual trigger is sufficient

## Consequences

**Easier:**
- Catches prompt regressions before they reach production
- Eval cases serve as living documentation of expected model behavior
- Can compare model versions side-by-side (e.g., testing a new OpenRouter model)
- Gives confidence to iterate on prompts without fear of silent degradation

**Harder:**
- LLM-as-judge assertions have their own failure modes (judge may disagree with itself)
- Maintaining eval cases as the analysis schema evolves
- Manual dispatch means someone has to remember to run it after prompt changes
- API cost per run (roughly 20 OpenRouter calls for generation + judge calls for grading)
