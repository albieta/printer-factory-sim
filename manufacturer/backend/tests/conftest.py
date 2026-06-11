from __future__ import annotations

import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool


for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.database import Base  # noqa: E402
from app.models.models import SimulationConfig, Product, ProductType, Inventory  # noqa: E402


@pytest.fixture
def db() -> Session:
    """Create an in-memory test database with schema and initial data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Seed initial config
    config = SimulationConfig(
        warehouse_capacity=2200,
        assembly_lines=1,
        workers_per_line=1,
        shift_hours=8.0,
        daily_assembly_hours=8.0,
        demand_distribution_mean=5.0,
        demand_distribution_variance=2.0,
        sim_date=date.today(),
        sim_day=0,
        cost_per_assembly_line=50000.0,
        cost_per_worker_per_hour=50.0,
        max_workers_per_line=10,
        total_costs=0.0,
        total_revenue=0.0,
    )
    session.add(config)

    # Seed starter materials
    materials = [
        "PLA Filament",
        "ABS Filament",
        "Aluminum Frame",
        "Stepper Motor",
        "Control Board",
        "LCD Screen",
    ]
    starter_inventory = {
        "PLA Filament": 500.0,
        "ABS Filament": 400.0,
        "Aluminum Frame": 200.0,
        "Stepper Motor": 300.0,
        "Control Board": 150.0,
        "LCD Screen": 100.0,
    }

    for material_name in materials:
        material = Product(name=material_name, type=ProductType.MATERIAL)
        session.add(material)
        session.flush()
        quantity = starter_inventory.get(material_name, 0.0)
        inventory = Inventory(product_id=material.id, quantity=Decimal(quantity))
        session.add(inventory)

    # Seed printers
    printers = [
        {"name": "Basic300", "assembly_hours": 2.0},
        {"name": "Pro450", "assembly_hours": 4.0},
        {"name": "Elite700", "assembly_hours": 6.0},
    ]
    for printer_data in printers:
        printer = Product(
            name=printer_data["name"],
            type=ProductType.PRINTER,
            assembly_hours=printer_data["assembly_hours"],
        )
        session.add(printer)

    session.commit()
    yield session
    session.close()
