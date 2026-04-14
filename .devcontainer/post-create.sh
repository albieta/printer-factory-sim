#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  python3 \
  python3-pip \
  python3-venv \
  curl \
  git

# Install uv if missing.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Ensure current shell can find uv installed to ~/.local/bin.
export PATH="$HOME/.local/bin:$PATH"

uv sync
