# ADR-011: Dependabot Over Renovate for Dependency Updates

**Status:** Accepted
**Date:** 2026-07-27
**Deciders:** cl-xy

## Context

Automated dependency updates keep the project secure and current. The two main options for GitHub-hosted projects are:

- **Dependabot:** Built into GitHub, zero setup beyond a config file, native security advisory integration
- **Renovate:** More configurable (automerge, custom grouping, regex managers), runs as a GitHub App or self-hosted

For this project, the dependency surface is moderate: one Python backend (pip), one Node frontend (npm), and GitHub Actions workflows.

## Decision

Use GitHub Dependabot. Configuration in `.github/dependabot.yml` with three package ecosystems:

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: "/backend"
    schedule:
      interval: weekly
    groups:
      dev-dependencies:
        patterns: ["pytest*", "ruff", "mypy"]

  - package-ecosystem: npm
    directory: "/frontend"
    schedule:
      interval: weekly
    groups:
      dev-dependencies:
        patterns: ["@types/*", "vitest", "oxlint"]

  - package-ecosystem: github-actions
    directory: "/"
    schedule:
      interval: weekly
```

## Consequences

**Easier:**
- Zero additional tooling: Dependabot is built into every GitHub repo
- Native integration with GitHub security alerts and vulnerability database
- PRs are straightforward: one PR per update (or grouped), easy to review
- No external app to authorize, no bot account to manage
- Grouped updates reduce PR noise for related packages

**Harder:**
- Less flexible than Renovate for complex grouping or automerge rules
- No regex managers for non-standard dependency files (not needed here)
- Cannot pin GitHub Actions to commit SHAs automatically (manual step)
- Limited scheduling options compared to Renovate's cron syntax
- No "dashboard issue" summarizing pending updates (Renovate feature)

These tradeoffs are acceptable at this project's scale. If the project grows to many more ecosystems or needs automerge with CI gates, Renovate would be worth reconsidering.
