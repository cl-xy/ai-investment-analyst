# Contributing

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (for PostgreSQL)
- A Groq API key (free tier works): https://console.groq.com/keys

## Quick Setup

```bash
./scripts/dev.sh
```

This handles everything: postgres, venv, deps, backend, frontend. On first run it creates `.env` from the example file. Fill in your API keys and run again.

## Development Workflow

1. Branch from `main`
2. Make changes
3. Run `./scripts/lint.sh` to verify code quality
4. Run tests: `make test`
5. Commit with conventional commit style
6. Push and open a PR

## Testing

```bash
# Backend (pytest)
cd backend && pytest -q --tb=short

# Frontend (vitest)
cd frontend && npx vitest run

# Both
make test-all
```

## Commit Conventions

Lowercase conventional commits. Keep them short and descriptive.

```
feat: add sse streaming endpoint
fix: handle null price in chart component
refactor: extract cache logic into service
test: add coverage for circuit breaker
docs: update API examples in readme
chore: bump ruff to 0.5.1
```

## PR Checklist

- [ ] Tests pass (`make test`)
- [ ] Lint clean (`./scripts/lint.sh`)
- [ ] No new security findings (`./scripts/security-scan.sh`)
- [ ] Docs updated if API surface changed

## Architecture Overview

FastAPI backend with LangGraph agent orchestration. Four MCP tool servers (market, news, portfolio, SEC). Groq free tier for LLM inference. SSE streaming to a React frontend with Zustand state management.

For detailed architecture, see `docs/ARCHITECTURE.md`.

## Code Style

- Python: ruff (linting + formatting), mypy (types). Config in `backend/pyproject.toml`.
- TypeScript: oxlint, strict tsc. Tailwind for styles.
- Pre-commit hooks enforce these automatically. Run `make hooks` to install.
