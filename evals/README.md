# LLM Evaluation Suite

Automated evaluation of the investment analyst's LLM behavior using [promptfoo](https://promptfoo.dev).

## What it tests

**39 total test cases** across 5 evaluation files:

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

**evals/edge-cases.yaml** (10 cases):
- Extreme valuations (pre-profit, penny stocks, halted trading)
- Data staleness detection (30-day-old data flagged)
- Boundary values (RSI >90, negative EPS)
- Sector diversity (REITs, biotech, ETFs)
- Conflicting sources (news vs fundamentals disagreement)

**evals/reasoning-quality.yaml** (7 cases):
- Confidence calibration (consensus data = high confidence, conflicting = not high)
- Logical consistency (sell signal aligns with bear case strength, sentiment matches signal)
- Risk flag quality (debt, concentration risk identified)
- No recency bias (single-day drop doesn't override strong fundamentals)

**evals/degradation.yaml** (6 cases):
- Complete data absence (all sources timeout)
- Single source available (only price data)
- Corrupted/malformed data (NaN, null, empty strings)
- Partial source failures (SEC missing, news errors)

## Running locally

```bash
# Requires OPENROUTER_API_KEY in your environment
npx promptfoo eval --config promptfooconfig.yaml

# View results in browser
npx promptfoo view

# Run specific test file only
npx promptfoo eval --config promptfooconfig.yaml --tests evals/safety.yaml
npx promptfoo eval --config promptfooconfig.yaml --tests evals/edge-cases.yaml
```

Or via Makefile:
```bash
make eval-llm
```

## Cost and rate limits

Each full run makes ~39 API calls to OpenRouter (one per test case). At current OpenRouter free tier limits:
- Token usage: ~200K tokens per run
- Request count: 39 requests (may need 2 minutes to stay within 20 req/min limit)
- Cost: $0 (OpenRouter free tier)
- Duration: ~2-4 minutes (rate-limited pacing)

Safe to run locally. If running the app simultaneously, space out requests to avoid hitting the 20 req/min ceiling.

## CI integration

Configured as a **manual-dispatch** workflow, not on every PR. Reasons:
- LLM outputs are nondeterministic (same prompt can produce different valid responses)
- API availability is external dependency (OpenRouter outages would fail CI)
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

## Test categories and what they catch

| Category | Catches | Example failure |
|----------|---------|-----------------|
| Structured output | Schema violations, missing fields | Model returns markdown instead of JSON |
| Factual grounding | Hallucinated numbers, ignored data | Price cited as $200 when data says $192 |
| Citations | Fabricated sources, wrong source_ids | Citation to "yfinance" for a news claim |
| Balanced reasoning | One-sided analysis, overconfidence | All-bullish data with zero bear_case |
| Safety | Prompt injection, guarantee language | Injection in news causes "buy" signal |
| Edge cases | Crashes on unusual inputs | Negative EPS throws validation error |
| Reasoning quality | Logical inconsistencies | Sell signal with positive sentiment_score |
| Degradation | Crashes on missing data | Empty indicators field causes invalid JSON |
