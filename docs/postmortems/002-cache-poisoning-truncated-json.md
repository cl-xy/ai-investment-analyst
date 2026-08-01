# Incident 002: Cache Poisoning from Truncated LLM JSON

**Date:** 2026-04-22
**Duration:** ~4 hours (silent data corruption)
**Severity:** SEV-3 (data quality degradation, no service outage)
**Correlation ID:** `corr_2d4f6a8b-0c1e-4a3c-5b7d-9e1f3a5b7c9d`

## Summary

The nemotron-120b model returned truncated JSON when a response hit the `max_tokens` ceiling. The `extract_json()` regex fallback extracted a partial object that happened to pass Pydantic validation because the missing fields (`bear_case`, `risk_flags`) were typed as `Optional`. This malformed result was cached with a 4-hour TTL. Users requesting TSLA analysis during that window received an incomplete report with no bear case or risk assessment.

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 09:14 | TSLA analysis triggered by a user. Nemotron-120b begins generating structured output. |
| 09:16 | LLM response hits `max_tokens` limit (4096 tokens). Response truncated mid-JSON, cutting off `bear_case` and `risk_flags` fields. |
| 09:16 | Primary JSON parse fails (unclosed braces). Fallback `extract_json()` regex finds the largest `{...}` substring, returns partial object. |
| 09:16 | Pydantic validation passes: `bear_case` and `risk_flags` are `Optional[...]`, so `None` defaults apply. No validation error raised. |
| 09:16 | Partial result cached in PostgreSQL with 4-hour TTL. Cache key: `analysis:TSLA:full`. |
| 09:16 - 13:14 | All TSLA requests served from cache. Users see analysis with missing bear case and empty risk section. |
| 12:47 | User reports via demo feedback: "TSLA analysis doesn't show any bear case, seems incomplete." |
| 12:55 | I check the cached entry, confirm `bear_case` is null and `risk_flags` is empty array. |
| 13:01 | Manually invalidate the TSLA cache entry. Next request triggers fresh analysis. |
| 13:03 | Fresh analysis completes with full JSON (including bear case). Confirm the report renders correctly. |
| 13:14 | Original poisoned cache entry would have expired naturally (4h TTL from 09:16). |

## Root Cause

Three factors combined:

1. **No `max_tokens` guard on the analysis prompt.** The TSLA analysis (a long-form ticker with extensive data) produced output exceeding the 4096 token limit. The response was silently truncated by the API without any error signal (just `finish_reason: "length"` in the response metadata, which we weren't checking).

2. **Regex fallback masked the parse failure.** When `json.loads()` failed on the truncated string, `extract_json()` used a regex to find the largest JSON-like substring. It found a valid-ish subset by matching the outermost braces up to the last valid closing brace before truncation.

3. **Optional fields hid the data loss.** The Pydantic model typed `bear_case`, `risk_flags`, and `key_risks` as Optional. The partial object had these as missing keys, which Pydantic defaulted to `None` / `[]`. Validation passed without complaint.

## Impact

- TSLA analysis served without bear case or risk flags for approximately 3.5 hours
- Estimated 12 unique users saw the incomplete analysis (based on request logs)
- No other tickers affected (TSLA's verbose output was uniquely long enough to hit the token limit)
- No service outage, no errors in logs (the failure was silent)

## Resolution

Immediate (same day):
1. Manually invalidated the poisoned cache entry
2. Added `finish_reason` check: if response has `finish_reason: "length"`, treat as failure and retry with higher `max_tokens`

Follow-up (next 3 days):
3. Added JSON completeness validation: verify all required top-level keys are present before caching, regardless of Pydantic Optional typing
4. Added cache-on-read validation: re-validate cached entries against schema on retrieval, invalidate if they fail the completeness check
5. Increased `max_tokens` from 4096 to 8192 for analysis calls
6. Changed `bear_case` and `risk_flags` from Optional to required in the analysis schema (they should never be missing in a complete analysis)
7. Added `data_completeness_score` field to cached entries for monitoring

## Lessons Learned

1. **Optional fields in your schema are a validation blind spot.** If a field should always be present in a complete response, it shouldn't be Optional even if the LLM occasionally omits it. Use required fields and handle LLM omissions with retries, not permissive types.

2. **Always check `finish_reason`.** The OpenRouter/OpenAI API tells you when output was truncated via `finish_reason: "length"`. Ignoring this field means you can't distinguish a complete response from a cut-off one.

3. **Regex JSON extraction is dangerous as a silent fallback.** The `extract_json()` helper should log a warning or increment a metric when it activates, so we know the primary parse path failed. Silent fallbacks hide problems.

4. **Cache writes need validation beyond "does this parse."** The bar for caching should be higher than the bar for accepting a response. A response might be parseable but incomplete, and caching amplifies the damage window from one request to thousands.

5. **4-hour TTL for LLM outputs is too long without integrity checks.** Either shorten the TTL, add validation on read, or both.

## Action Items

| Item | Status | Date |
|------|--------|------|
| Check `finish_reason` on all LLM responses | Done | 2026-04-22 |
| Add completeness validation before cache write | Done | 2026-04-23 |
| Cache-on-read revalidation | Done | 2026-04-23 |
| Increase `max_tokens` to 8192 for analysis calls | Done | 2026-04-22 |
| Make `bear_case` and `risk_flags` required fields | Done | 2026-04-24 |
| Add metric for `extract_json()` fallback activations | Done | 2026-04-24 |
| Audit all Optional fields in analysis schema for correctness | Done | 2026-04-25 |
