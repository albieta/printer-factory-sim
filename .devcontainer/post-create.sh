#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

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
  cd "$ROOT_DIR/frontend"
  npm ci
)

(
  cd "$ROOT_DIR/backend"
  "$ROOT_DIR/.venv/bin/python" scripts/seed_data.py
)
