"""Constants and helpers for the retailer's starter profile.

The starter profile is the canonical "fresh retailer" state used by:

- the seed loader (`retailer/scripts/seed_data.py`),
- future test fixtures,
- a future "reset" CLI/REST action.

The seed JSON file (`retailer/seed/seed-retailer.json`) is the
human-editable surface; this module is just where Python code reaches
when it needs the same data without re-reading the file.

Printer-model names are aligned with the manufacturer's starter profile
(`manufacturer/backend/app/services/starter_profile.py:STARTER_PRINTERS`)
so the Week 7 turn-engine smoke scenario in `docs/PRD-week7.md` §10.1
can run without manual stitching.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
"""Bumped when the seed JSON schema or the retailer's REST contract
changes in a backward-incompatible way. See `docs/PRD-week7.md` §9."""

INITIAL_DAY = 0
"""Retailer's simulated day 0 (matches the manufacturer's initial day)."""

DEFAULT_MARKUP_PCT = 30
"""Default retail markup over wholesale (percent). See PRD-week7 §4.4."""

MINIMUM_MARKUP_PCT = 10
"""Hard floor on markup. `price set` must reject anything below this.
See PRD-week7 §4.4. Agent adjusts prices based on demand above this floor."""


def seed_file_path() -> Path:
    """Absolute path to the canonical seed JSON file."""

    return Path(__file__).resolve().parents[2] / "seed" / "seed-retailer.json"


def load_seed_data() -> dict[str, Any]:
    """Read and parse the seed JSON file.

    Returns the raw dict. Validation lives in the seed loader script;
    this function is intentionally narrow.
    """

    with seed_file_path().open(encoding="utf-8") as handle:
        return dict(json.load(handle))
