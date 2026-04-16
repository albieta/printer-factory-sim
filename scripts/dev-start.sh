#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
  echo "Missing Python virtual environment at $ROOT_DIR/.venv" >&2
  echo "Run the devcontainer setup or create it manually before starting the app." >&2
  exit 1
fi

if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  echo "Missing frontend dependencies in $ROOT_DIR/frontend/node_modules" >&2
  echo "Run 'cd frontend && npm ci' before starting the app." >&2
  exit 1
fi

cleanup() {
  jobs -p | xargs -r kill >/dev/null 2>&1 || true
  wait || true
}

trap cleanup EXIT INT TERM

(
  cd "$ROOT_DIR/backend"
  exec "$ROOT_DIR/.venv/bin/python" -m uvicorn main:app --host 0.0.0.0 --port 8000
) &
backend_pid=$!

(
  cd "$ROOT_DIR/frontend"
  exec npm run dev -- --host 0.0.0.0 --port 3000
) &
frontend_pid=$!

echo "Frontend: http://localhost:3000"
echo "API docs: http://localhost:8000/docs"
echo "Press Ctrl+C to stop both services."

wait -n "$backend_pid" "$frontend_pid"
