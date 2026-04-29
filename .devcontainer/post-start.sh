#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="/tmp/printer-factory-sim"
LOCK_FILE="$LOG_DIR/post-start.lock"
SETUP_COMPLETE_FILE="$LOG_DIR/post-create-complete"
DEPENDENCY_WAIT_SECONDS="${DEPENDENCY_WAIT_SECONDS:-180}"
STARTUP_WAIT_SECONDS="${STARTUP_WAIT_SECONDS:-60}"

mkdir -p "$LOG_DIR"
exec 9>"$LOCK_FILE"

if ! flock -n 9; then
  exit 0
fi

is_port_listening() {
  local port="$1"
  ss -ltn | grep -q ":$port "
}

wait_for_http() {
  local url="$1"
  local timeout_seconds="$2"
  local waited=0

  while [ "$waited" -lt "$timeout_seconds" ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi

    sleep 1
    waited=$((waited + 1))
  done

  return 1
}

workspace_ready() {
  [ -f "$SETUP_COMPLETE_FILE" ] && return 0
  [ -x "$ROOT_DIR/.venv/bin/python" ] && [ -x "$ROOT_DIR/manufacturer/frontend/node_modules/.bin/vite" ]
}

wait_for_workspace() {
  local timeout_seconds="$1"
  local waited=0

  while [ "$waited" -lt "$timeout_seconds" ]; do
    if workspace_ready; then
      return 0
    fi

    sleep 1
    waited=$((waited + 1))
  done

  return 1
}

if ! wait_for_workspace "$DEPENDENCY_WAIT_SECONDS"; then
  echo "Workspace setup did not complete within ${DEPENDENCY_WAIT_SECONDS}s." >&2
  exit 1
fi

start_backend() {
  nohup bash -lc "cd '$ROOT_DIR/manufacturer/backend' && exec '$ROOT_DIR/.venv/bin/python' -m uvicorn main:app --host 0.0.0.0 --port 8000" \
    >"$LOG_DIR/backend.log" 2>&1 < /dev/null &
}

start_frontend() {
  nohup bash -lc "cd '$ROOT_DIR/manufacturer/frontend' && exec ./node_modules/.bin/vite --host 0.0.0.0 --port 3000 --strictPort" \
    >"$LOG_DIR/frontend.log" 2>&1 < /dev/null &
}

if ! is_port_listening 8000; then
  start_backend
fi

if ! wait_for_http "http://127.0.0.1:8000/health" "$STARTUP_WAIT_SECONDS"; then
  echo "Backend failed to start on port 8000. See $LOG_DIR/backend.log for details." >&2
  exit 1
fi

if ! is_port_listening 3000; then
  start_frontend
fi

if ! wait_for_http "http://127.0.0.1:3000" "$STARTUP_WAIT_SECONDS"; then
  echo "Frontend failed to start on port 3000. See $LOG_DIR/frontend.log for details." >&2
  exit 1
fi
