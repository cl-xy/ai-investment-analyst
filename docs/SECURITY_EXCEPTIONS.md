# Security Exceptions

Documented security findings that have been reviewed and accepted as tolerable risk. Each exception has an owner, an expiry date, and a compensating control.

Machine-readable format: [`security-exceptions.yaml`](../security-exceptions.yaml)

## Process: Adding a New Exception

1. Identify the finding (tool name, rule ID, affected file).
2. Determine why the finding is a false positive or accepted risk.
3. Document the compensating control (what prevents this from becoming a real issue).
4. Set an expiry date (max 6 months out).
5. Add to `security-exceptions.yaml` and update this table.
6. Get a review from a second pair of eyes before merging.

## Review Cadence

Quarterly, or when any exception's expiry date passes. On review: re-evaluate whether the exception is still valid, extend or remove as appropriate.

## Current Exceptions

| ID | Tool | Finding | Reason | Expires |
|----|------|---------|--------|---------|
| SEC-001 | detect-secrets | High entropy strings in test fixtures | Synthetic market data triggers entropy detection. Not real secrets. | 2027-01-27 |
| SEC-002 | hadolint | DL3008 (unversioned apt packages) | Base image pinned by SHA256 digest, which locks the OS layer. | 2027-01-27 |
| SEC-003 | cors-audit | Localhost origins in CORS allow list | Localhost on a public deployment is not exploitable. Production origin added via env var. | 2027-01-27 |
| SEC-004 | npm-audit | @types/react-router-dom deprecated | Build-time only types package. No runtime code ships. Tracked for removal. | 2027-01-27 |
