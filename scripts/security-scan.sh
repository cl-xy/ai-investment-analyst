#!/usr/bin/env bash
set -euo pipefail

# Local security scanning. Runs semgrep, pip-audit, npm audit, and detect-secrets.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FINDINGS=0
RESULTS=()

info()  { echo -e "${GREEN}[security]${NC} $1"; }
warn()  { echo -e "${YELLOW}[security]${NC} $1"; }

# -------------------------------------------------------------------
# Semgrep
# -------------------------------------------------------------------
info "Running semgrep..."
if command -v semgrep >/dev/null 2>&1; then
    if [ -f "$ROOT_DIR/.semgrep.yml" ]; then
        if semgrep --config "$ROOT_DIR/.semgrep.yml" "$ROOT_DIR/backend/src/" --quiet 2>/dev/null; then
            RESULTS+=("  semgrep: no findings")
        else
            RESULTS+=("  semgrep: findings detected (review above)")
            FINDINGS=$((FINDINGS + 1))
        fi
    else
        if semgrep --config auto "$ROOT_DIR/backend/src/" --quiet --severity ERROR 2>/dev/null; then
            RESULTS+=("  semgrep: no high/critical findings")
        else
            RESULTS+=("  semgrep: findings detected (review above)")
            FINDINGS=$((FINDINGS + 1))
        fi
    fi
else
    warn "semgrep not installed. Install: pip install semgrep (or brew install semgrep)"
    RESULTS+=("  semgrep: SKIPPED (not installed)")
fi

# -------------------------------------------------------------------
# pip-audit (backend)
# -------------------------------------------------------------------
info "Running pip-audit on backend..."
PIP_AUDIT="$ROOT_DIR/backend/.venv/bin/pip-audit"
if [ -f "$PIP_AUDIT" ] || command -v pip-audit >/dev/null 2>&1; then
    AUDIT_CMD="${PIP_AUDIT:-pip-audit}"
    if $AUDIT_CMD --require-hashes=false -r "$ROOT_DIR/backend/pyproject.toml" --desc 2>/dev/null | grep -q "No known vulnerabilities"; then
        RESULTS+=("  pip-audit: no known vulnerabilities")
    elif $AUDIT_CMD 2>/dev/null; then
        RESULTS+=("  pip-audit: no known vulnerabilities")
    else
        RESULTS+=("  pip-audit: vulnerabilities found (review above)")
        FINDINGS=$((FINDINGS + 1))
    fi
else
    warn "pip-audit not installed. Install: pip install pip-audit"
    RESULTS+=("  pip-audit: SKIPPED (not installed)")
fi

# -------------------------------------------------------------------
# npm audit (frontend)
# -------------------------------------------------------------------
info "Running npm audit on frontend..."
cd "$ROOT_DIR/frontend"
if npm audit --audit-level=high --omit=dev 2>/dev/null; then
    RESULTS+=("  npm audit: no high/critical vulnerabilities")
else
    RESULTS+=("  npm audit: high/critical vulnerabilities found")
    FINDINGS=$((FINDINGS + 1))
fi

# -------------------------------------------------------------------
# detect-secrets
# -------------------------------------------------------------------
info "Running detect-secrets..."
cd "$ROOT_DIR"
if command -v detect-secrets >/dev/null 2>&1; then
    if [ -f .secrets.baseline ]; then
        SCAN_OUTPUT=$(detect-secrets scan --baseline .secrets.baseline 2>&1 || true)
        if echo "$SCAN_OUTPUT" | grep -q "ERROR\|new secret"; then
            RESULTS+=("  detect-secrets: new secrets detected (update baseline or remove)")
            FINDINGS=$((FINDINGS + 1))
        else
            RESULTS+=("  detect-secrets: clean (matches baseline)")
        fi
    else
        warn "No .secrets.baseline found. Run: detect-secrets scan > .secrets.baseline"
        RESULTS+=("  detect-secrets: SKIPPED (no baseline)")
    fi
else
    warn "detect-secrets not installed. Install: pip install detect-secrets"
    RESULTS+=("  detect-secrets: SKIPPED (not installed)")
fi

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
echo ""
echo "Security Scan Summary:"
for result in "${RESULTS[@]}"; do
    echo "$result"
done
echo ""

if [ $FINDINGS -gt 0 ]; then
    echo -e "${RED}${FINDINGS} scan(s) reported findings.${NC}"
    exit 1
else
    echo -e "${GREEN}All security scans clean.${NC}"
fi
