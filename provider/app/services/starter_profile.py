"""Constants and helpers for the provider's starter profile.

The starter profile is the canonical "fresh provider" state used by:

- the seed loader (`provider/scripts/seed_data.py`),
- future test fixtures,
- a future "reset" CLI/REST action.

The seed JSON file (`provider/seed/seed-provider.json`) is the
human-editable surface; this module is just where Python code reaches
when it needs the same data without re-reading the file.

Material names are aligned with the manufacturer's BOM
(`manufacturer/backend/app/services/starter_profile.py:STARTER_MATERIALS`)
so the Week 6 five-day scenario in `docs/PRD-week6.md` §8 can run
without manual stitching.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
"""Bumped when the seed JSON schema or the provider's REST contract
changes in a backward-incompatible way. See `docs/PRD-week6.md` §7."""

INITIAL_DAY = 0
"""Provider's simulated day 0 (matches the manufacturer's initial day)."""


def seed_file_path() -> Path:
    """Absolute path to the canonical seed JSON file."""

    return Path(__file__).resolve().parents[2] / "seed" / "seed-provider.json"


def load_seed_data() -> dict[str, Any]:
    """Read and parse the seed JSON file.

    Returns the raw dict. Validation lives in the seed loader script;
    this function is intentionally narrow.
    """

    with seed_file_path().open(encoding="utf-8") as handle:
        return json.load(handle)
