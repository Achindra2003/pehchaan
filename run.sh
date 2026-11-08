#!/usr/bin/env bash
set -Eeuo pipefail

# Pehchaan Unified Runner Script
# Sets up dependencies, environment files, models, and starts backend + frontend services with logging.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
LOG_DIR="$ROOT_DIR/logs"
API_DIR="$ROOT_DIR/api"
WEB_DIR="$ROOT_DIR/web"

mkdir -p "$LOG_DIR"

API_LOG="$LOG_DIR/api.log"
WEB_LOG="$LOG_DIR/web.log"
MAIN_LOG="$LOG_DIR/run.log"

# Color helpers
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BOLD="\033[1m"
NC="\033[0m"

log() {
  local timestamp
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
  echo -e "${BLUE}[$timestamp]${NC} $1" | tee -a "$MAIN_LOG"
}

log_success() {
  local timestamp
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
  echo -e "${GREEN}[$timestamp] ✔ $1${NC}" | tee -a "$MAIN_LOG"
}

log_warn() {
  local timestamp
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
  echo -e "${YELLOW}[$timestamp] ⚠ $1${NC}" | tee -a "$MAIN_LOG"
}

log_error() {
  local timestamp
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
  echo -e "${RED}[$timestamp] ✖ $1${NC}" | tee -a "$MAIN_LOG" >&2
}

# Cleanup on exit or interrupt
API_PID=""
WEB_PID=""

cleanup() {
  echo ""
  log_warn "Stopping running services..."
  if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
  fi
  if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill "$WEB_PID" 2>/dev/null || true
  fi
  wait "$API_PID" 2>/dev/null || true
  wait "$WEB_PID" 2>/dev/null || true
  log "All services stopped."
  exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}   Pehchaan · All-in-One Runner Script  ${NC}"
echo -e "${BOLD}========================================${NC}"
log "Log directory: $LOG_DIR"

# 1. Check prerequisite tools
log "Checking required system tools..."
MISSING_TOOLS=()
command -v uv >/dev/null 2>&1 || MISSING_TOOLS+=("uv (install via https://astral.sh/uv)")
command -v npm >/dev/null 2>&1 || MISSING_TOOLS+=("npm / nodejs (install Node 18+)")

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
  log_error "Missing required tools:"
  for tool in "${MISSING_TOOLS[@]}"; do
    echo -e "  - $tool"
  done
  exit 1
fi
log_success "Prerequisites check passed (uv and npm found)."

# 2. Setup Environment Variables
log "Checking environment files..."
if [ ! -f "$API_DIR/.env" ]; then
  if [ -f "$ROOT_DIR/.env.example" ]; then
    log_warn "api/.env not found. Creating from .env.example..."
    cp "$ROOT_DIR/.env.example" "$API_DIR/.env"
    log_success "Created api/.env"
  elif [ -f "$API_DIR/.env.example" ]; then
    log_warn "api/.env not found. Creating from api/.env.example..."
    cp "$API_DIR/.env.example" "$API_DIR/.env"
    log_success "Created api/.env"
  fi
else
  log_success "api/.env already exists."
fi

# 3. Setup Backend (api)
log "Syncing backend Python virtual environment and dependencies..."
(
  cd "$API_DIR"
  uv sync
) >> "$MAIN_LOG" 2>&1
log_success "Backend dependencies synced."

# 4. Check & Download Models
log "Checking ONNX models..."
(
  cd "$API_DIR"
  uv run python scripts/download_models.py
) >> "$MAIN_LOG" 2>&1
log_success "Model check completed."

# 5. Setup Frontend (web)
log "Checking frontend dependencies..."
if [ ! -d "$WEB_DIR/node_modules" ]; then
  log_warn "web/node_modules not found. Installing npm packages..."
  (
    cd "$WEB_DIR"
    npm install
  ) >> "$MAIN_LOG" 2>&1
  log_success "Frontend packages installed."
else
  log_success "web/node_modules found."
fi

# 6. Start Backend API
log "Starting backend API server on http://localhost:8000 (logging to $API_LOG)..."
(
  cd "$API_DIR"
  exec uv run uvicorn pehchaan.main:app_factory --factory --reload --port 8000
) > "$API_LOG" 2>&1 &
API_PID=$!

# Wait for backend to be ready
BACKEND_READY=false
log "Waiting for backend API healthcheck..."
for i in {1..30}; do
  if curl -s http://localhost:8000/healthz >/dev/null 2>&1 || curl -s http://localhost:8000/docs >/dev/null 2>&1; then
    BACKEND_READY=true
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    log_error "Backend server crashed during startup. Check $API_LOG for details."
    cat "$API_LOG"
    exit 1
  fi
  sleep 1
done

if [ "$BACKEND_READY" = true ]; then
  log_success "Backend is up and running at http://localhost:8000 (Docs: http://localhost:8000/docs)"
else
  log_warn "Backend healthcheck did not respond in 30s, but process is running. Proceeding..."
fi

# 7. Start Frontend (web)
log "Starting frontend dev server on http://localhost:5173 (logging to $WEB_LOG)..."
(
  cd "$WEB_DIR"
  exec npm run dev -- --host 0.0.0.0
) > "$WEB_LOG" 2>&1 &
WEB_PID=$!

# Wait briefly to ensure vite didn't instantly exit
sleep 2
if ! kill -0 "$WEB_PID" 2>/dev/null; then
  log_error "Frontend server crashed during startup. Check $WEB_LOG for details."
  cat "$WEB_LOG"
  exit 1
fi
log_success "Frontend dev server is running (Logs: $WEB_LOG)"

echo ""
echo -e "${GREEN}${BOLD}======================================================${NC}"
echo -e "${GREEN}${BOLD}   Pehchaan services are running successfully!       ${NC}"
echo -e "${GREEN}${BOLD}======================================================${NC}"
echo -e " • ${BOLD}Frontend App:${NC}       http://localhost:5173"
echo -e " • ${BOLD}Backend API:${NC}        http://localhost:8000"
echo -e " • ${BOLD}API Documentation:${NC}  http://localhost:8000/docs"
echo -e " • ${BOLD}API Logs:${NC}           $API_LOG"
echo -e " • ${BOLD}Frontend Logs:${NC}      $WEB_LOG"
echo -e " • ${BOLD}Runner Log:${NC}         $MAIN_LOG"
echo ""
echo -e "Press ${BOLD}Ctrl+C${NC} to gracefully stop all services."
echo ""

# Tail logs or wait for interrupt
wait
