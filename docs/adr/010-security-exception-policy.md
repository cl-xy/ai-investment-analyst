# ADR-010: Security Exception Policy with Machine-Readable YAML

**Status:** Accepted
**Date:** 2026-07-27
**Deciders:** cl-xy

## Context

Security scanners (Semgrep, pip-audit, npm audit, detect-secrets) produce findings that are sometimes false positives or accepted risks. Without a formal process, these get handled one of three ways:

1. Inline `# nosec` / `# noqa` comments with no explanation (opaque)
2. Ignored entirely (scan output becomes noise everyone tunes out)
3. Fixed unnecessarily (wasting time on non-issues)

I need a way to explicitly acknowledge accepted findings, document why they are acceptable, and ensure exceptions don't live forever.

## Decision

Create `security-exceptions.yaml` at the repo root with this schema:

```yaml
exceptions:
  - id: SEC-001
    tool: semgrep
    rule: custom.missing-await-async-db
    location: backend/src/agent/nodes/fetch_data.py:42
    reason: "This call is intentionally fire-and-forget for cache warming"
    compensating_control: "Background task has its own error handler and retry"
    owner: cl-xy
    expires: 2026-10-27
```

Required fields per exception:
- `id`: unique identifier (SEC-NNN)
- `tool`: which scanner produced the finding
- `rule` or `finding`: the specific rule/CVE/advisory
- `location`: file and line (or package name for dependency findings)
- `reason`: why this is acceptable (not just "false positive")
- `compensating_control`: what mitigates the risk
- `owner`: who approved this exception
- `expires`: when this must be re-evaluated (max 90 days)

CI validation (in the security job):
- Parse the YAML, check no exception has an `expires` date in the past
- Fail the build if any exception is expired (forces re-evaluation)
- Count total active exceptions and warn if over 10

## Consequences

**Easier:**
- Exceptions are auditable: anyone can read the file and understand what risks are accepted
- Time-bounded: expired exceptions force re-evaluation, preventing permanent ignore
- Machine-readable: CI can enforce the policy automatically
- Demonstrates security maturity in the codebase

**Harder:**
- Overhead of writing a YAML entry for each exception (intentionally: friction discourages lazy suppression)
- Need to keep `location` fields updated when code moves (or use package-level references)
- 90-day max expiry means periodic review work even for persistent false positives
