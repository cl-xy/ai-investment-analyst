#!/usr/bin/env bash
set -euo pipefail

# Local quality gate that mirrors CI checks.
# Runs all linters and type checkers for backend and frontend.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS="${GREEN}PASS${NC}"
FAIL="${RED}FAIL${NC}"

FAILURES=0
RESULTS=()

run_check() {
    local name="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        RESULTS+=("  $PASS  $name")
    else
        RESULTS+=("  $FAIL  $name")
        FAILURES=$((FAILURES + 1))
    fi
}

echo "Running quality checks..."
echo ""

# -------------------------------------------------------------------
# Backend checks
# -------------------------------------------------------------------
BACKEND_DIR="$ROOT_DIR/backend"
PYTHON="$BACKEND_DIR/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo -e "${YELLOW}[lint]${NC} No backend venv found. Run ./scripts/dev.sh first."
    exit 1
fi

RUFF="$BACKEND_DIR/.venv/bin/ruff"
MYPY="$BACKEND_DIR/.venv/bin/mypy"

run_check "ruff check (backend)" "$RUFF" check "$BACKEND_DIR/src/"
run_check "ruff format (backend)" "$RUFF" format --check "$BACKEND_DIR/src/"
run_check "mypy (backend)" "$MYPY" "$BACKEND_DIR/src/" --ignore-missing-imports --no-error-summary

# -------------------------------------------------------------------
# Frontend checks
# -------------------------------------------------------------------
FRONTEND_DIR="$ROOT_DIR/frontend"

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo -e "${YELLOW}[lint]${NC} No frontend node_modules found. Run npm install first."
    exit 1
fi

run_check "oxlint (frontend)" npx --prefix "$FRONTEND_DIR" oxlint "$FRONTEND_DIR/src/"
run_check "tsc --noEmit (frontend)" npx --prefix "$FRONTEND_DIR" tsc --noEmit --project "$FRONTEND_DIR/tsconfig.json"

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
echo ""
echo "Results:"
for result in "${RESULTS[@]}"; do
    echo -e "$result"
done
echo ""

if [ $FAILURES -gt 0 ]; then
    echo -e "${RED}${FAILURES} check(s) failed.${NC}"
    exit 1
else
    echo -e "${GREEN}All checks passed.${NC}"
fi
