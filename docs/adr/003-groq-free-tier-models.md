# ADR-003: Groq Free Tier with GPT-OSS Models

**Status:** Accepted
**Date:** 2026-07-05
**Deciders:** cl-xy

## Context

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
