# ADR-003: Groq Free Tier with GPT-OSS Models

**Status:** Superseded (migrated to OpenRouter, 2026-07-27)
**Date:** 2026-07-05
**Deciders:** cl-xy

## Context

> **Note:** This ADR is historical. The project migrated from Groq to OpenRouter in July 2026 (see commit `bd72e73`). The reasoning below reflects the original decision to use Groq. OpenRouter now serves as the LLM provider with the same model routing strategy (fast model for intent classification, capable model for analysis).

This is a portfolio project demonstrating multi-agent investment analysis. It needs to be runnable without incurring API costs, both for development iteration and for anyone cloning the repo to try it out.

I need two model tiers: a fast, cheap model for intent routing, and a capable model for deep analysis and report generation.

## Decision

Use Groq's free tier with GPT-OSS models:
- `openai/gpt-oss-20b` for the router (intent classification, tool selection)
- `openai/gpt-oss-120b` for analysis and report generation

Reasons:

- Free tier means zero cost for development and demos. Anyone can sign up and run the system.
- Groq's inference speed (tokens/sec) is exceptional, which directly improves streaming UX. Users see results flowing in rather than waiting.
- JSON mode is supported, enabling structured output for Pydantic validation without prompt-hacking.
- The 20B model is fast enough for routing that it doesn't bottleneck the pipeline.
- The 120B model produces analysis quality sufficient for a demo, even if it's not GPT-4 class.

## Superseded By

Migrated to OpenRouter (https://openrouter.ai) which provides:
- Broader model selection with the same free tier economics
- OpenAI-compatible API (drop-in replacement via langchain-openai)
- Same models available (`openai/gpt-oss-20b:free`, `nvidia/nemotron-3-super-120b-a12b:free`)
- 20 req/min rate limit on free tier

## Consequences

**Easier:**
- Zero cost to run, develop, and demo.
- Fast inference makes SSE streaming feel responsive.
- No billing surprises during development.
- Low barrier for others to try the project.

**Harder:**
- Rate limits are real. Budget guard system is mandatory to avoid 429s.
- Model quality ceiling is lower than commercial alternatives.
- Free tier may change or disappear, requiring a fallback strategy.
- Rate limits mean concurrent users can starve each other without the budget exhaustion fallback.
