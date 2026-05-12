#!/usr/bin/env python3
"""Seed loader for the provider app.

Reads `provider/seed/seed-provider.json` and populates the SQLite
database with products, pricing tiers, initial stock, and the starting
simulated day. Idempotent: running it on an already-seeded database
exits without duplicating rows.

Run from the `provider/` directory so the SQLite file lands at
`provider/provider.db`:

    cd provider
    ../.venv/bin/python scripts/seed_data.py
"""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.models import (  # noqa: E402
    PricingTier,
    Product,
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

    products = seed.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("Seed file must contain a non-empty 'products' list.")

    for entry in products:
        for required in ("name", "lead_time_days", "pricing", "initial_stock"):
            if required not in entry:
                raise ValueError(
                    f"Product entry {entry!r} missing required field {required!r}."
                )

        if entry["lead_time_days"] < 1:
            # Enforces the Week 6 "ironclad rule" for seed data, too.
            raise ValueError(
                f"Product {entry['name']!r} has lead_time_days < 1; "
                "minimum lead time is 1 day."
            )

        pricing = entry["pricing"]
        if not isinstance(pricing, list) or not pricing:
            raise ValueError(
                f"Product {entry['name']!r} must have at least one pricing tier."
            )

        # Pricing tiers must start at 1 so any positive quantity has a price.
        if min(tier["min_qty"] for tier in pricing) != 1:
            raise ValueError(
                f"Product {entry['name']!r} pricing tiers must start at min_qty=1."
            )


def seed_database() -> None:
    seed = load_seed_data()
    validate_seed(seed)

    db = SessionLocal()

    try:
        if db.query(Product).count() > 0:
            print("Provider database already seeded. Skipping...")
            return

        print("Seeding provider database...")

        for entry in seed["products"]:
            product = Product(
                name=entry["name"],
                description=entry.get("description"),
                lead_time_days=entry["lead_time_days"],
            )
            db.add(product)
            db.flush()  # populate product.id before we reference it

            for tier in entry["pricing"]:
                db.add(
                    PricingTier(
                        product_id=product.id,
                        min_quantity=tier["min_qty"],
                        unit_price=tier["unit_price"],
                    )
                )

            db.add(
                Stock(
                    product_id=product.id,
                    quantity=entry["initial_stock"],
                )
            )

        initial_day = seed.get("initial_day", INITIAL_DAY)
        db.add(SimState(key="current_day", value=str(initial_day)))

        db.commit()

        print(f"  Loaded {len(seed['products'])} products with pricing tiers and stock")
        print(f"  Simulation day initialised to {initial_day}")
        print("Done.")
    except Exception as exc:
        db.rollback()
        print(f"Error seeding provider database: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
