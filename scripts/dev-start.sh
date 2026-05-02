#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROVIDER_PORT="${PROVIDER_PORT:-8001}"
DEFAULT_BACKEND_PORT="${BACKEND_PORT:-8002}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
STARTUP_WAIT_SECONDS="${STARTUP_WAIT_SECONDS:-60}"

if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
  echo "Missing Python virtual environment at $ROOT_DIR/.venv" >&2
  echo "Run the devcontainer setup or create it manually before starting the app." >&2
  exit 1
fi

if [ ! -d "$ROOT_DIR/manufacturer/frontend/node_modules" ]; then
  echo "Missing frontend dependencies in $ROOT_DIR/manufacturer/frontend/node_modules" >&2
  echo "Run 'cd manufacturer/frontend && npm ci' before starting the app." >&2
  exit 1
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

find_available_port() {
  local starting_port="$1"
  "$ROOT_DIR/.venv/bin/python" - "$starting_port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
while port < 65536:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            port += 1
            continue
    print(port)
    break
else:
    raise SystemExit("No available port found")
PY
}

cleanup() {
  jobs -p | xargs -r kill >/dev/null 2>&1 || true
  wait || true
}

trap cleanup EXIT INT TERM

backend_started=false
frontend_started=false
provider_started=false

if is_port_listening "$PROVIDER_PORT"; then
  :
else
  (
    cd "$ROOT_DIR/provider"
    "$ROOT_DIR/.venv/bin/python" scripts/seed_data.py
    cd "$ROOT_DIR"
    exec "$ROOT_DIR/.venv/bin/python" -m provider.cli serve --port "$PROVIDER_PORT"
  ) &
  provider_pid=$!
  provider_started=true
fi

if is_port_listening "$DEFAULT_BACKEND_PORT"; then
  BACKEND_PORT="$DEFAULT_BACKEND_PORT"
else
  BACKEND_PORT="$(find_available_port "$DEFAULT_BACKEND_PORT")"
  export VITE_BACKEND_PORT="$BACKEND_PORT"

  (
    cd "$ROOT_DIR/manufacturer/backend"
    exec "$ROOT_DIR/.venv/bin/python" -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload --reload-dir "$ROOT_DIR/manufacturer/backend"
  ) &
  backend_pid=$!
  backend_started=true
fi

if is_port_listening "$FRONTEND_PORT"; then
  :
else
  export VITE_BACKEND_PORT="$BACKEND_PORT"

  (
    cd "$ROOT_DIR/manufacturer/frontend"
    exec ./node_modules/.bin/vite --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort
  ) &
  frontend_pid=$!
  frontend_started=true
fi

if ! wait_for_http "http://127.0.0.1:$PROVIDER_PORT/health" "$STARTUP_WAIT_SECONDS"; then
  echo "Provider on port $PROVIDER_PORT did not become ready within ${STARTUP_WAIT_SECONDS}s." >&2
  exit 1
fi

if ! wait_for_http "http://127.0.0.1:$BACKEND_PORT/health" "$STARTUP_WAIT_SECONDS"; then
  echo "Backend on port $BACKEND_PORT did not become ready within ${STARTUP_WAIT_SECONDS}s." >&2
  exit 1
fi

if ! wait_for_http "http://127.0.0.1:$FRONTEND_PORT" "$STARTUP_WAIT_SECONDS"; then
  echo "Frontend on port $FRONTEND_PORT did not become ready within ${STARTUP_WAIT_SECONDS}s." >&2
  exit 1
fi

echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "Manufacturer API docs: http://localhost:$BACKEND_PORT/docs"
echo "Provider API docs: http://localhost:$PROVIDER_PORT/docs"
if [ "$provider_started" = false ]; then
  echo "Provider already running on $PROVIDER_PORT, reusing it."
  echo "If provider code changed, restart the existing server so the running API matches the files on disk."
fi
if [ "$backend_started" = false ]; then
  echo "Backend already running on $BACKEND_PORT, reusing it."
  echo "If backend code changed, restart the existing server so the running API matches the files on disk."
elif [ "$BACKEND_PORT" != "$DEFAULT_BACKEND_PORT" ]; then
  echo "Backend port $DEFAULT_BACKEND_PORT was busy, so the API started on $BACKEND_PORT."
fi
if [ "$frontend_started" = false ]; then
  echo "Frontend already running on $FRONTEND_PORT, reusing it."
fi
echo "Press Ctrl+C to stop services started by this script."

pids=()
if [ "$provider_started" = true ]; then
  pids+=("$provider_pid")
fi
if [ "$backend_started" = true ]; then
  pids+=("$backend_pid")
fi
if [ "$frontend_started" = true ]; then
  pids+=("$frontend_pid")
fi

if [ "${#pids[@]}" -gt 0 ]; then
  wait -n "${pids[@]}"
fi
