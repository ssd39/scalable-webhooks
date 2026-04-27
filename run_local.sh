#!/usr/bin/env bash
##############################################################################
# run_local.sh
#
# Local development entry-point.
#
# Normal mode (no flags):
#   1. Ensures Docker infrastructure (PostgreSQL + Redis) is running.
#   2. Creates / activates a Python virtual environment.
#   3. Installs / upgrades Python dependencies.
#   4. Copies .env.example → .env if .env does not exist yet.
#   5. Waits until PostgreSQL and Redis are reachable.
#   6. Runs Alembic migrations (alembic upgrade head).
#   7. Starts the RQ worker in the background.
#   8. Starts the Uvicorn dev server (foreground, auto-reload).
#   9. On exit (Ctrl-C / error) stops the background worker.
#
# Test mode (--test [...]):
#   Runs test_gen.py after setting up the venv and loading .env.
#   Any extra flags are forwarded directly to test_gen.py.
#
#   Examples:
#     ./run_local.sh --test
#     ./run_local.sh --test --shipment
#     ./run_local.sh --test --invoice --count 3
#     ./run_local.sh --test --unclassified
##############################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()    { echo -e "${GREEN}[run_local]${RESET} $*"; }
warning() { echo -e "${YELLOW}[run_local]${RESET} $*"; }
error()   { echo -e "${RED}[run_local]${RESET} $*" >&2; }

# ── Parse --test flag + collect pass-through args ────────────────────────────
TEST_MODE=false
TEST_ARGS=()

for arg in "$@"; do
  if [ "$arg" = "--test" ]; then
    TEST_MODE=true
  else
    TEST_ARGS+=("$arg")
  fi
done

# ── 1. Start infrastructure ───────────────────────────────────────────────────
info "Starting infrastructure (PostgreSQL + Redis) …"
docker compose -f docker-compose.infra.yml up -d

# ── 2. Virtual environment ────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
  info "Creating Python virtual environment …"
  python3 -m venv venv
fi

info "Activating virtual environment …"
# shellcheck disable=SC1091
source venv/bin/activate

# ── 3. Install dependencies ───────────────────────────────────────────────────
info "Installing / upgrading Python dependencies …"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# ── 4. .env file ─────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  warning ".env not found – copying from .env.example"
  cp .env.example .env
fi

# Load env vars
set -o allexport
# shellcheck disable=SC1091
source .env
set +o allexport

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-glacias}"
POSTGRES_DB="${POSTGRES_DB:-glacias}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

# ── TEST MODE: run test_gen.py and exit ───────────────────────────────────────
if [ "$TEST_MODE" = true ]; then
  info "Test mode – running test_gen.py ${TEST_ARGS[*]+"${TEST_ARGS[*]}"}"
  python test_gen.py "${TEST_ARGS[@]+"${TEST_ARGS[@]}"}"
  exit $?
fi

# ── 5. Wait for PostgreSQL ────────────────────────────────────────────────────
info "Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT} …"
MAX_TRIES=30
COUNT=0
until docker exec glacias_postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q 2>/dev/null; do
  COUNT=$((COUNT + 1))
  if [ "$COUNT" -ge "$MAX_TRIES" ]; then
    error "PostgreSQL did not become ready in time. Aborting."
    exit 1
  fi
  sleep 1
done
info "PostgreSQL is ready ✓"

# ── Wait for Redis ────────────────────────────────────────────────────────────
info "Waiting for Redis at ${REDIS_HOST}:${REDIS_PORT} …"
COUNT=0
until docker exec glacias_redis redis-cli ping 2>/dev/null | grep -q PONG; do
  COUNT=$((COUNT + 1))
  if [ "$COUNT" -ge "$MAX_TRIES" ]; then
    error "Redis did not become ready in time. Aborting."
    exit 1
  fi
  sleep 1
done
info "Redis is ready ✓"

# ── 6. Run Alembic migrations ─────────────────────────────────────────────────
info "Running database migrations (alembic upgrade head) …"
alembic upgrade head

# ── 7. Start background worker ────────────────────────────────────────────────
info "Starting RQ worker in the background …"
python -m app.worker.listener &
WORKER_PID=$!
info "Worker started (PID: ${WORKER_PID})"

# ── Cleanup on exit ───────────────────────────────────────────────────────────
cleanup() {
  info "Shutting down worker (PID: ${WORKER_PID}) …"
  kill "$WORKER_PID" 2>/dev/null || true
  wait "$WORKER_PID" 2>/dev/null || true
  info "Done. Infrastructure containers are still running."
  info "To stop them: docker compose -f docker-compose.infra.yml down"
}
trap cleanup EXIT INT TERM

# ── 8. Start API server ───────────────────────────────────────────────────────
info "Starting Uvicorn dev server → http://localhost:8000"
info "API docs → http://localhost:8000/docs"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
