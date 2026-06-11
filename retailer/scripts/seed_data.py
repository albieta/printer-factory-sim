#!/usr/bin/env python3
"""Seed loader for the retailer app.

Reads `retailer/seed/seed-retailer.json` and populates the SQLite
database with the catalog, initial finished-printer stock, and the
starting simulated day. Idempotent: running it on an already-seeded
database exits without duplicating rows.

Run from the `retailer/` directory so the SQLite file lands at
`retailer/retailer.db`:

    cd retailer
    ../.venv/bin/python scripts/seed_data.py
"""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.models import (  # noqa: E402
    CatalogEntry,
    SimState,
    Stock,
)
from app.services.starter_profile import (  # noqa: E402
    INITIAL_DAY,
    SCHEMA_VERSION,
    load_seed_data,
)
from app.utils.database import SessionLocal, bootstrap_database  # noqa: E402


bootstrap_database()


def validate_seed(seed: dict[str, Any]) -> None:
    """Fail fast on a malformed seed file before we touch the DB."""

    if seed.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Seed schema_version {seed.get('schema_version')!r} does not "
            f"match the loader's expected version {SCHEMA_VERSION}. "
            "Update either the JSON or the loader."
        )

    catalog = seed.get("catalog")
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("Seed file must contain a non-empty 'catalog' list.")

    seen_names: set[str] = set()
    for entry in catalog:
        for required in ("product_name", "retail_price", "initial_stock"):
            if required not in entry:
                raise ValueError(
                    f"Catalog entry {entry!r} missing required field {required!r}."
                )

        name = entry["product_name"]
        if name in seen_names:
            raise ValueError(f"Duplicate catalog entry for product_name {name!r}.")
        seen_names.add(name)

        if entry["retail_price"] <= 0:
            raise ValueError(
                f"Catalog entry {name!r} has retail_price <= 0; must be positive."
            )

        if entry["initial_stock"] < 0:
            raise ValueError(
                f"Catalog entry {name!r} has initial_stock < 0; must be non-negative."
            )


def seed_database() -> None:
    seed = load_seed_data()
    validate_seed(seed)

    db = SessionLocal()

    try:
        if db.query(CatalogEntry).count() > 0:
            print("Retailer database already seeded. Skipping...")
            return

        print("Seeding retailer database...")

        for entry in seed["catalog"]:
            db.add(
                CatalogEntry(
                    product_name=entry["product_name"],
                    description=entry.get("description"),
                    retail_price=entry["retail_price"],
                )
            )
            db.add(
                Stock(
                    product_name=entry["product_name"],
                    quantity=entry["initial_stock"],
                )
            )

        initial_day = seed.get("initial_day", INITIAL_DAY)
        db.add(SimState(key="current_day", value=str(initial_day)))

        db.commit()

        print(f"  Loaded {len(seed['catalog'])} catalog entries with retail prices and stock")
        print(f"  Simulation day initialised to {initial_day}")
        print("Done.")
    except Exception as exc:
        db.rollback()
        print(f"Error seeding retailer database: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
