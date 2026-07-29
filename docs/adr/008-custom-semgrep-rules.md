# ADR-008: Custom Semgrep Rules Over Generic Presets

**Status:** Accepted
**Date:** 2026-07-27
**Deciders:** cl-xy

## Context

I need security scanning in CI that catches real risks specific to this stack (FastAPI + OpenRouter + asyncpg + FastMCP) without flooding PRs with irrelevant findings. Generic SAST rulesets (like `p/python` or `p/owasp-top-ten`) produce noise: they flag patterns that don't apply here (e.g., Django ORM injection rules) while missing patterns that do (e.g., f-string prompt injection, missing await on async DB calls).

The goal is high signal-to-noise. Every finding should be actionable for this project.

## Decision

Write 10-12 project-specific Semgrep rules targeting patterns that actually matter in this codebase:

- **Prompt injection via f-strings:** flag any f-string or `.format()` that interpolates user input into LLM prompts
- **SQL interpolation:** flag string concatenation or f-strings in asyncpg `execute`/`fetch` calls (must use parameterized queries)
- **Missing await on async DB:** flag `pool.execute()` without `await` (easy mistake, silent failure)
- **Unvalidated tool output:** flag direct use of MCP tool results without Pydantic validation
- **Secrets in source:** flag hardcoded API keys, tokens, or passwords (backup for .secrets.baseline)
- **Broad exception swallowing:** flag bare `except:` or `except Exception` without logging
- **Missing timeout on HTTP calls:** flag `httpx.get`/`aiohttp` calls without explicit timeout
- **SSE without buffering header:** flag StreamingResponse without `X-Accel-Buffering: no`
- **OpenRouter call without JSON mode:** flag OpenRouter chat completions for structured output nodes missing `response_format`
- **Mutable default in Pydantic:** flag `list` or `dict` as default values instead of `default_factory`

Rules live in `.semgrep/` directory. CI runs them with `semgrep --config .semgrep/`.

## Consequences

**Easier:**
- Every CI finding is relevant and actionable for this specific codebase
- Rule messages teach the "why" behind each pattern, onboarding new contributors
- Rules serve as executable documentation of security requirements
- Fast execution (10-12 rules vs hundreds in generic packs)

**Harder:**
- Maintenance burden: rules need updating when code patterns evolve
- No coverage for patterns I haven't thought of (generic rulesets cast a wider net)
- Writing good Semgrep patterns takes iteration and testing
- New team members need to understand the custom rules exist alongside standard tooling
