# LLM Evaluation Suite

Automated evaluation of the investment analyst's LLM behavior using [promptfoo](https://promptfoo.dev).

## What it tests

**evals/investment-analyst.yaml** (13 cases):
- Structured output compliance: valid JSON schema, correct ticker, bounded fields
- Factual grounding: references actual provided numbers, acknowledges contradictions, flags stale data
- Citation quality: source_ids match provided data, price claims cite yfinance, news claims cite newsapi
- Balanced reasoning: bullish data still gets bear_case, bearish data still gets bull_case, mixed signals get medium/low confidence

**evals/safety.yaml** (5 cases):
- Direct prompt injection in ticker field
- Indirect injection via news headline containing instructions
- Refusal to guarantee returns
- System prompt disclosure resistance
- No absolute future price predictions

## Running locally

```bash
# Requires GROQ_API_KEY in your environment
npx promptfoo eval --config promptfooconfig.yaml

# View results in browser
npx promptfoo view

# Run specific test file only
npx promptfoo eval --config promptfooconfig.yaml --tests evals/safety.yaml
```

Or via Makefile:
```bash
make eval-llm
```

## Cost and rate limits

Each full run makes ~18 API calls to Groq (one per test case). At current Groq free tier limits:
- Token usage: ~100K tokens per run (well within 250K TPM limit)
- Request count: 18 requests (well within 1K RPM limit)
- Cost: $0 (Groq free tier)
- Duration: ~30-60 seconds

Safe to run multiple times locally. No risk of hitting rate limits unless you're simultaneously running the app with heavy traffic.

## CI integration

Configured as a **manual-dispatch** workflow, not on every PR. Reasons:
- LLM outputs are nondeterministic (same prompt can produce different valid responses)
- API availability is external dependency (Groq outages would fail CI)
- Eval assertions use tolerant checks (schema validation, content presence) rather than exact string matching

Run manually before prompt changes to catch regressions.

## Adding new test cases

Each test case needs:
- `vars`: input variables matching the prompt template placeholders
- `assert`: one or more assertions (is-json, contains, not-contains, javascript, llm-rubric)

Use `llm-rubric` sparingly (for qualitative checks). Prefer deterministic `javascript` assertions for schema validation and field checks.

## Interpreting results

- Green: all assertions pass
- Red: at least one assertion failed
- `is-json` failure: model returned non-JSON (check if max_tokens is set)
- `javascript` failure: schema field missing or out of bounds
- `llm-rubric` failure: qualitative check disagreement (review manually, may be false positive)
