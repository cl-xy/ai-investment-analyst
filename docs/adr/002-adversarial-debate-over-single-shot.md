# ADR-002: Adversarial Debate Over Single-Shot Analysis

**Status:** Accepted  
**Date:** 2025-04-02

## Context

Investment analysis requires balanced perspectives. A single LLM call tends toward confirmation bias: if the prompt frames a ticker positively (recent price increase, strong revenue), the model reinforces that frame. Early prototypes produced analyses that were consistently bullish regardless of underlying risk factors.

I needed a mechanism that forces the model to argue both sides with citations, then synthesize a verdict with explicit rationale for why one side's arguments are stronger.

## Decision

Replace the single-shot `analyze_ticker` node with a 3-agent sequential debate:

1. **Bull** (argues the long case with citations from fetched data)
2. **Bear** (rebuts bull's arguments, argues the short case)
3. **Moderator** (weighs both sides, delivers verdict with confidence score and rationale)

Each agent uses OpenRouter JSON mode + Pydantic validation (`BullCaseOutput`, `BearCaseOutput`, `ModeratorOutput` schemas). On validation failure, one retry is attempted. If the full debate fails or the circuit breaker trips, the system falls back to single-shot analysis.

Implementation: `backend/src/agent/nodes/debate.py` with a 4-second minimum delay between sequential calls to avoid burst contention on free-tier workers.

## Reasons

- **Reduces single-model bias.** Forcing explicit argumentation for both sides produces more balanced analysis than asking one prompt to "consider risks."
- **Structured citations per side.** Each agent must reference specific data points (P/E ratio, revenue growth, debt levels). This creates auditable reasoning.
- **Moderator resolves with rationale.** The verdict isn't just "buy" or "sell" but includes explicit reasoning about which arguments were more compelling and why.
- **Pydantic schemas enforce structure.** `BullCaseOutput`, `BearCaseOutput`, and `ModeratorOutput` guarantee consistent output shape regardless of model creativity.

## Consequences

**Positive:**
- Analyses are measurably more balanced (validated in promptfoo eval suite, 18 cases)
- Users see the debate unfold in real-time via SSE events (`debate_update`)
- Evidence drawer in the UI shows bull vs bear arguments side by side
- Fallback to single-shot means the system never fully fails

**Negative:**
- 3x latency: ~90-120s total vs ~30-40s for single-shot (3 sequential LLM calls at 30-40s each)
- 3x rate limit consumption on OpenRouter free tier (20 req/min shared across all users)
- Circuit breaker (`backend/src/agent/circuit_breaker.py`) trips more easily under load because one analysis uses 3 slots
- More complex error handling: partial debate failures (bull succeeds, bear fails) need graceful degradation
