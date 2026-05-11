#!/usr/bin/env python3
"""Seed loader for the retailer app.

Reads `retailer/seed/seed-retailer.json` and populates the SQLite
database with catalog items and zero initial stock. Idempotent: running
it on an already-seeded database exits without duplicating rows.

Usage (from the repo root):

    .venv/bin/python retailer/scripts/seed_data.py [--config retailer.json]

The --config flag selects the retailer instance to seed; defaults to
`retailer.json` in the current working directory.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

# Allow `python retailer/scripts/seed_data.py` from the repo root.
RETAILER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RETAILER_ROOT))

import argparse  # noqa: E402

from app.models.models import CatalogItem, SimState, Stock  # noqa: E402
from app.utils.config import load_config  # noqa: E402
from app.utils.database import bootstrap_database, get_session_factory  # noqa: E402

SEED_PATH = RETAILER_ROOT / "seed" / "seed-retailer.json"
SCHEMA_VERSION = 1


def validate_seed(seed: dict[str, Any]) -> None:
    """Fail fast on a malformed seed file before touching the DB."""
    if seed.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Seed schema_version {seed.get('schema_version')!r} != "
            f"expected {SCHEMA_VERSION}."
        )
    catalog = seed.get("catalog")
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("Seed file must contain a non-empty 'catalog' list.")
    for entry in catalog:
        for field in ("model_name", "retail_price", "initial_stock"):
            if field not in entry:
                raise ValueError(
                    f"Catalog entry {entry!r} missing required field {field!r}."
                )
        if Decimal(str(entry["retail_price"])) <= 0:
            raise ValueError(
                f"Model {entry['model_name']!r} retail_price must be positive."
            )


def seed_database(config_path: Path) -> None:
    cfg = load_config(config_path)
    bootstrap_database(cfg.db_path)

    seed: dict[str, Any] = json.loads(SEED_PATH.read_text())
    validate_seed(seed)

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        if db.query(CatalogItem).count() > 0:
            print("Retailer database already seeded. Skipping.")
            return

        print("Seeding retailer database...")

        for entry in seed["catalog"]:
            item = CatalogItem(
                model_name=entry["model_name"],
                retail_price=Decimal(str(entry["retail_price"])),
            )
            db.add(item)
            db.flush()

            db.add(Stock(catalog_item_id=item.id, quantity=entry["initial_stock"]))

        initial_day = seed.get("initial_day", 0)
        db.add(SimState(key="current_day", value=str(initial_day)))

        db.commit()

        print(f"  Loaded {len(seed['catalog'])} catalog items with zero stock")
        print(f"  Simulation day initialised to {initial_day}")
        print("Done.")
    except Exception as exc:
        db.rollback()
        print(f"Error seeding retailer database: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the retailer database.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("retailer.json"),
        help="Path to retailer config JSON (default: retailer.json)",
    )
    args = parser.parse_args()
    seed_database(args.config)
