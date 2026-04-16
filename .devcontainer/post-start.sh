#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="/tmp/printer-factory-sim"

mkdir -p "$LOG_DIR"

if [ ! -x "$ROOT_DIR/.venv/bin/python" ] || [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  echo "Workspace dependencies are missing. Rebuild the container to rerun post-create setup." >&2
  exit 0
fi

if ! pgrep -f "uvicorn main:app --host 0.0.0.0 --port 8000" >/dev/null; then
  setsid -f bash -lc "cd '$ROOT_DIR/backend' && exec '$ROOT_DIR/.venv/bin/python' -m uvicorn main:app --host 0.0.0.0 --port 8000"     >"$LOG_DIR/backend.log" 2>&1
fi

if ! pgrep -f "vite --host 0.0.0.0 --port 3000" >/dev/null; then
  setsid -f bash -lc "cd '$ROOT_DIR/frontend' && exec npm run dev -- --host 0.0.0.0 --port 3000"     >"$LOG_DIR/frontend.log" 2>&1
fi
