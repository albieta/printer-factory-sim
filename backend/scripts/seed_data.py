#!/usr/bin/env python3
"""Seed data script for the 3D Printer Production Simulator."""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.models import BillOfMaterials, Inventory, Product, ProductType, SimulationConfig, Supplier
from app.services.starter_profile import (
    STARTER_BOM,
    STARTER_INVENTORY,
    STARTER_MATERIALS,
    STARTER_PRINTERS,
    STARTER_SUPPLIERS,
    build_starter_config,
)
from app.utils.database import SessionLocal, bootstrap_database


bootstrap_database()


def seed_database() -> None:
    db = SessionLocal()

    try:
        existing_config = db.query(SimulationConfig).first()
        if existing_config and db.query(Product).count() and db.query(Supplier).count():
            print("Database already seeded. Skipping...")
            return

        print("Seeding database...")

        config = existing_config or SimulationConfig(**build_starter_config(sim_date=date.today()))
        if not existing_config:
            db.add(config)
            db.commit()
        print("✓ Created simulation config")

        product_lookup: dict[str, Product] = {}

        for printer_data in STARTER_PRINTERS:
            printer = Product(
                name=printer_data["name"],
                type=ProductType.PRINTER,
                assembly_hours=printer_data["assembly_hours"],
            )
            db.add(printer)
            product_lookup[printer.name] = printer
        db.commit()
        print(f"✓ Created {len(STARTER_PRINTERS)} printer models")

        for material_name in STARTER_MATERIALS:
            material = Product(name=material_name, type=ProductType.MATERIAL)
            db.add(material)
            product_lookup[material.name] = material
        db.commit()
        print(f"✓ Created {len(STARTER_MATERIALS)} materials")

        bom_count = 0
        for printer_name, entries in STARTER_BOM.items():
            for entry in entries:
                db.add(
                    BillOfMaterials(
                        finished_product_id=product_lookup[printer_name].id,
                        material_id=product_lookup[entry["material"]].id,
                        quantity=entry["quantity"],
                    )
                )
                bom_count += 1
        db.commit()
        print(f"✓ Created {bom_count} BOM entries")

        for supplier_data in STARTER_SUPPLIERS:
            db.add(
                Supplier(
                    name=supplier_data["name"],
                    product_id=product_lookup[supplier_data["product"]].id,
                    unit_cost=supplier_data["unit_cost"],
                    lead_time_days=supplier_data["lead_time_days"],
                    quantity_breaks=supplier_data["quantity_breaks"],
                )
            )
        db.commit()
        print(f"✓ Created {len(STARTER_SUPPLIERS)} suppliers")

        for material_name, quantity in STARTER_INVENTORY.items():
            db.add(Inventory(product_id=product_lookup[material_name].id, quantity=quantity))
        db.commit()
        print("✓ Initialized inventory with starting stock")

        print("\n✓ Database seeding completed successfully!")
        print(f"\nSimulation start date: {date.today()}")
    except Exception as exc:
        db.rollback()
        print(f"✗ Error seeding database: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
