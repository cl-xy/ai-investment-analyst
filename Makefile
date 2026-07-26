.PHONY: hooks lint test dev security test-all eval-llm clean

dev:
	./scripts/dev.sh

hooks:
	pre-commit install
	pre-commit run --all-files

lint:
	./scripts/lint.sh

security:
	./scripts/security-scan.sh

test:
	cd backend && .venv/bin/pytest -q --tb=short
	cd frontend && npx vitest run

test-all: lint test

eval-llm:
	npx promptfoo eval --config promptfooconfig.yaml

clean:
	rm -rf backend/.venv
	rm -rf frontend/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
