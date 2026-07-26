#!/usr/bin/env bash
set -euo pipefail

# One-command local dev startup for ai-investment-analyst.
# Starts postgres, backend (uvicorn), and frontend (vite).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[dev]${NC} $1"; }
warn()  { echo -e "${YELLOW}[dev]${NC} $1"; }
error() { echo -e "${RED}[dev]${NC} $1"; exit 1; }

# Track background PIDs for cleanup
PIDS=()
cleanup() {
    info "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
    info "Done."
}
trap cleanup EXIT INT TERM

# -------------------------------------------------------------------
# Prerequisites
# -------------------------------------------------------------------
info "Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || error "python3 not found. Install Python 3.11+."
command -v node >/dev/null 2>&1    || error "node not found. Install Node.js 20+."
command -v docker >/dev/null 2>&1  || error "docker not found. Install Docker Desktop."

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
NODE_VERSION=$(node --version | sed 's/v//' | cut -d. -f1)

info "Python ${PYTHON_VERSION}, Node ${NODE_VERSION}"

# -------------------------------------------------------------------
# Environment file
# -------------------------------------------------------------------
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        warn ".env created from .env.example. Fill in your API keys before running again."
        warn "Required: GROQ_API_KEY, NEWS_API_KEY"
        exit 1
    else
        error "No .env or .env.example found."
    fi
fi

# -------------------------------------------------------------------
# Start PostgreSQL via docker compose
# -------------------------------------------------------------------
info "Starting PostgreSQL..."
docker compose up -d postgres

info "Waiting for PostgreSQL to be ready..."
RETRIES=30
until docker compose exec -T postgres pg_isready -U invest -d investment_analyst >/dev/null 2>&1; do
    RETRIES=$((RETRIES - 1))
    if [ $RETRIES -le 0 ]; then
        error "PostgreSQL failed to start within 30 seconds."
    fi
    sleep 1
done
info "PostgreSQL is ready."

# -------------------------------------------------------------------
# Backend: venv + deps
# -------------------------------------------------------------------
cd "$ROOT_DIR/backend"

if [ ! -d .venv ]; then
    info "Creating Python virtual environment..."
    python3 -m venv .venv
fi

PYTHON="$ROOT_DIR/backend/.venv/bin/python"
PIP="$ROOT_DIR/backend/.venv/bin/pip"

# Install deps if pyproject.toml is newer than .venv marker
MARKER="$ROOT_DIR/backend/.venv/.deps_installed"
if [ ! -f "$MARKER" ] || [ pyproject.toml -nt "$MARKER" ]; then
    info "Installing backend dependencies..."
    $PIP install -q -e ".[dev]"
    touch "$MARKER"
fi

# -------------------------------------------------------------------
# Database schema init (run migrations if available)
# -------------------------------------------------------------------
if [ -d "$ROOT_DIR/backend/migrations" ]; then
    info "Running database migrations..."
    $PYTHON -m alembic upgrade head 2>/dev/null || warn "No alembic config found, skipping migrations."
else
    info "No migrations directory found, skipping schema init."
fi

# -------------------------------------------------------------------
# Start backend
# -------------------------------------------------------------------
info "Starting backend (uvicorn :8000)..."
cd "$ROOT_DIR/backend"
$ROOT_DIR/backend/.venv/bin/uvicorn src.api.main:app --reload --port 8000 &
PIDS+=($!)

# Give uvicorn a moment to bind
sleep 2

# -------------------------------------------------------------------
# Frontend: deps + dev server
# -------------------------------------------------------------------
cd "$ROOT_DIR/frontend"

if [ ! -d node_modules ] || [ package.json -nt node_modules/.package-lock.json ]; then
    info "Installing frontend dependencies..."
    npm install
fi

# -------------------------------------------------------------------
# Start frontend (foreground)
# -------------------------------------------------------------------
info "Starting frontend (vite)..."
info "Backend:  http://localhost:8000"
info "Frontend: http://localhost:5173"
echo ""
npm run dev
