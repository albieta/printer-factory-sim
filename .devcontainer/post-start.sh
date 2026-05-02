#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$ROOT_DIR/.devcontainer/state"
LOG_DIR="/tmp/printer-factory-sim"
LOCK_FILE="$LOG_DIR/post-start.lock"
STACK_LOG_FILE="$LOG_DIR/full-stack.log"
SETUP_COMPLETE_FILE="$STATE_DIR/post-create-complete"
DEPENDENCY_WAIT_SECONDS="${DEPENDENCY_WAIT_SECONDS:-180}"
STARTUP_WAIT_SECONDS="${STARTUP_WAIT_SECONDS:-60}"

mkdir -p "$STATE_DIR"
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

workspace_missing_dependencies() {
  [ ! -x "$ROOT_DIR/.venv/bin/python" ] || [ ! -x "$ROOT_DIR/manufacturer/frontend/node_modules/.bin/vite" ]
}

wait_for_workspace() {
  local timeout_seconds="$1"
  local waited=0

  if workspace_missing_dependencies; then
    return 1
  fi

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
  if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
    echo "Warning: missing Python virtual environment at $ROOT_DIR/.venv. Rerun .devcontainer/post-create.sh to install dependencies." >&2
  elif [ ! -x "$ROOT_DIR/manufacturer/frontend/node_modules/.bin/vite" ]; then
    echo "Warning: missing frontend dependencies at $ROOT_DIR/manufacturer/frontend/node_modules. Rerun .devcontainer/post-create.sh to install dependencies." >&2
  else
    echo "Warning: workspace setup marker was not written within ${DEPENDENCY_WAIT_SECONDS}s. Rerun .devcontainer/post-create.sh if setup did not finish." >&2
  fi
  exit 0
fi

if ! is_port_listening 8001 || ! is_port_listening 8002 || ! is_port_listening 3000; then
  nohup bash "$ROOT_DIR/scripts/dev-start.sh" >"$STACK_LOG_FILE" 2>&1 < /dev/null &
fi

if ! wait_for_http "http://127.0.0.1:8001/health" "$STARTUP_WAIT_SECONDS"; then
  echo "Warning: provider did not become ready on port 8001 within ${STARTUP_WAIT_SECONDS}s. See $STACK_LOG_FILE for details." >&2
  exit 0
fi

if ! wait_for_http "http://127.0.0.1:8002/health" "$STARTUP_WAIT_SECONDS"; then
  echo "Warning: manufacturer backend did not become ready on port 8002 within ${STARTUP_WAIT_SECONDS}s. See $STACK_LOG_FILE for details." >&2
  exit 0
fi

if ! wait_for_http "http://127.0.0.1:3000" "$STARTUP_WAIT_SECONDS"; then
  echo "Warning: frontend did not become ready on port 3000 within ${STARTUP_WAIT_SECONDS}s. See $STACK_LOG_FILE for details." >&2
  exit 0
fi
