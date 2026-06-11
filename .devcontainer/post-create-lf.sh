#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$ROOT_DIR/.devcontainer/state"
SETUP_COMPLETE_FILE="$STATE_DIR/post-create-complete"
cd "$ROOT_DIR"

mkdir -p "$STATE_DIR"
rm -f "$SETUP_COMPLETE_FILE"

sudo apt-get update
sudo apt-get install -y --no-install-recommends   python3   python3-pip   python3-venv   ca-certificates   curl   git   gnupg

if ! command -v node >/dev/null 2>&1 || [ "$(node -p 'process.versions.node.split(`.`)[0]')" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y --no-install-recommends nodejs
fi

if [ ! -d "$ROOT_DIR/.venv" ]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi

"$ROOT_DIR/.venv/bin/pip" install --upgrade pip
"$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/requirements.txt"

(
  cd "$ROOT_DIR/manufacturer/frontend"
  npm ci
)

(
  cd "$ROOT_DIR/manufacturer/backend"
  "$ROOT_DIR/.venv/bin/python" scripts/seed_data.py
)

(
  cd "$ROOT_DIR/provider"
  "$ROOT_DIR/.venv/bin/python" scripts/seed_data.py
)

(
  cd "$ROOT_DIR/retailer"
  RETAILER_DB_URL="sqlite:///./retailer.db" \
  RETAILER_MANUFACTURER_URL="http://localhost:8002" \
  RETAILER_NAME="PrinterWorld" \
  RETAILER_MANUFACTURER_NAME="Factory" \
    "$ROOT_DIR/.venv/bin/python" scripts/seed_data.py
)

date -u +"%Y-%m-%dT%H:%M:%SZ" >"$SETUP_COMPLETE_FILE"
