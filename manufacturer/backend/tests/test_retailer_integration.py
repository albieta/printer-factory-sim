"""Tests for retailer-manufacturer integration: purchase order placement, delivery
pipeline, demand config persistence, and reset behaviour.

All tests use an in-memory SQLite database via the shared `db` fixture from
conftest.py.  No real HTTP calls are made.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]

import pytest  # noqa: E402

from app.models.models import (  # noqa: E402
    FinancialTransaction,
    FinancialTransactionType,
    ManufacturingOrder,
    OrderStatus,
    Product,
    ProductType,
    SalesOrder,
    SalesOrderStatus,
    SimulationConfig,
    WholesalePrice,
    Inventory,
    BillOfMaterials,
)
from app.services.config_service import ConfigService  # noqa: E402
from app.services.financial_service import FinancialService  # noqa: E402
from app.services.sales_order_service import SalesOrderService  # noqa: E402
from app.services.simulation_service import SimulationService  # noqa: E402
from app.services.wholesale_price_service import WholesalePriceService  # noqa: E402
from app.schemas.schemas import SimulationConfigUpdate  # noqa: E402
from app.utils.database import Base  # noqa: E402


# ── shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()

    config = SimulationConfig(
        warehouse_capacity=2200,
        assembly_lines=2,
        workers_per_line=2,
        shift_hours=8.0,
        daily_assembly_hours=8.0,
        demand_distribution_mean=5.0,
        demand_distribution_variance=2.0,
        sim_date=date(2026, 1, 1),
        sim_day=1,
        cost_per_assembly_line=50000.0,
        cost_per_worker_per_hour=50.0,
        max_workers_per_line=4,
        total_costs=0.0,
        total_revenue=0.0,
        retailer_demand_enabled=False,
        retailer_demand_mean=8.0,
        retailer_demand_variance=2.0,
        retailer_demand_modifier=1.0,
        retailer_demand_base_price=400.0,
    )
    session.add(config)

    materials = {
        "PLA Filament": 500.0, "ABS Filament": 400.0,
        "Aluminum Frame": 200.0, "Stepper Motor": 300.0,
        "Control Board": 150.0, "LCD Screen": 100.0,
    }
    for name, qty in materials.items():
        mat = Product(name=name, type=ProductType.MATERIAL)
        session.add(mat)
        session.flush()
        session.add(Inventory(product_id=mat.id, quantity=Decimal(str(qty))))

    for name, hrs in [("Basic300", 2.0), ("Pro450", 4.0), ("Elite700", 6.0)]:
        printer = Product(name=name, type=ProductType.PRINTER, assembly_hours=hrs)
        session.add(printer)

    session.commit()
    yield session
    session.close()


# ── helpers ───────────────────────────────────────────────────────────────────

def _seed_bom_and_prices(db: Session) -> dict[str, Product]:
    """Add minimal BOM entries and wholesale prices so production can run."""
    lookup: dict[str, Product] = {
        p.name: p for p in db.query(Product).all()
    }

    bom_data = {
        "Basic300": [("PLA Filament", 1.0), ("Aluminum Frame", 1.0),
                     ("Stepper Motor", 1.0), ("Control Board", 1.0)],
        "Pro450":   [("ABS Filament", 2.0), ("Aluminum Frame", 1.0),
                     ("Stepper Motor", 2.0), ("Control Board", 1.0)],
        "Elite700": [("ABS Filament", 3.0), ("Aluminum Frame", 2.0),
                     ("Stepper Motor", 3.0), ("Control Board", 2.0),
                     ("LCD Screen", 1.0)],
    }
    for printer, entries in bom_data.items():
        for mat, qty in entries:
            db.add(BillOfMaterials(
                finished_product_id=lookup[printer].id,
                material_id=lookup[mat].id,
                quantity=Decimal(str(qty)),
            ))

    for name, price in [("Basic300", "450.00"), ("Pro450", "800.00"), ("Elite700", "1400.00")]:
        db.add(WholesalePrice(product_id=lookup[name].id, price=Decimal(price)))

    db.commit()
    return lookup


# ── config persistence tests ──────────────────────────────────────────────────

def test_serialize_config_includes_retailer_demand_fields(db: Session) -> None:
    cfg = ConfigService(db).serialize_config()
    assert "retailer_demand_enabled" in cfg
    assert "retailer_demand_mean" in cfg
    assert "retailer_demand_variance" in cfg
    assert "retailer_demand_modifier" in cfg
    assert "retailer_demand_base_price" in cfg


def test_update_config_persists_retailer_demand_enabled(db: Session) -> None:
    svc = ConfigService(db)
    svc.update_config(SimulationConfigUpdate(retailer_demand_enabled=True))

    cfg = svc.serialize_config()
    assert cfg["retailer_demand_enabled"] is True


def test_update_config_retailer_demand_only_sets_given_fields(db: Session) -> None:
    """Partial update must not clobber unmentioned fields with defaults."""
    svc = ConfigService(db)
    svc.update_config(SimulationConfigUpdate(retailer_demand_mean=12.0))

    cfg = svc.serialize_config()
    assert cfg["retailer_demand_mean"] == 12.0
    # assembly config unchanged
    assert cfg["assembly_lines"] == 2
    assert cfg["workers_per_line"] == 2


def test_update_config_toggle_off_after_on(db: Session) -> None:
    svc = ConfigService(db)
    svc.update_config(SimulationConfigUpdate(retailer_demand_enabled=True))
    svc.update_config(SimulationConfigUpdate(retailer_demand_enabled=False))

    assert svc.serialize_config()["retailer_demand_enabled"] is False


# ── wholesale price seeding on reset ─────────────────────────────────────────

def test_wholesale_price_seeded_after_reset_to_default_config(db: Session) -> None:
    sim = SimulationService(db)
    sim.reset_to_default_config()

    prices = WholesalePriceService(db).list_prices()
    assert prices.get("Basic300") == Decimal("450.00")
    assert prices.get("Pro450") == Decimal("800.00")
    assert prices.get("Elite700") == Decimal("1400.00")


def test_wholesale_price_no_orphan_rows_after_reset(db: Session) -> None:
    """After reset, WholesalePrice rows match current product IDs."""
    _seed_bom_and_prices(db)
    sim = SimulationService(db)
    sim.reset_to_default_config()

    # All WholesalePrice rows should have a matching Product.
    orphans = db.query(WholesalePrice).all()
    product_ids = {p.id for p in db.query(Product).all()}
    for row in orphans:
        assert row.product_id in product_ids, f"Orphaned WholesalePrice for {row.product_id}"


# ── financial transaction cleared on reset ────────────────────────────────────

def test_reset_simulation_clears_financial_transactions(db: Session) -> None:
    fin = FinancialService(db)
    fin.record_product_sold(1, 450.0, "Basic300", 1)
    fin.record_product_sold(2, 800.0, "Pro450", 1)
    assert db.query(FinancialTransaction).count() == 2

    SimulationService(db).reset_simulation()

    assert db.query(FinancialTransaction).count() == 0


def test_reset_to_empty_clears_financial_transactions(db: Session) -> None:
    fin = FinancialService(db)
    fin.record_product_sold(1, 450.0, "Basic300", 1)
    assert db.query(FinancialTransaction).count() == 1

    SimulationService(db).reset_to_empty()

    assert db.query(FinancialTransaction).count() == 0


def test_reset_to_default_config_clears_financial_transactions(db: Session) -> None:
    fin = FinancialService(db)
    fin.record_product_sold(1, 1400.0, "Elite700", 1)
    assert db.query(FinancialTransaction).count() == 1

    SimulationService(db).reset_to_default_config()

    assert db.query(FinancialTransaction).count() == 0


def test_reset_simulation_resets_revenue_and_costs(db: Session) -> None:
    fin = FinancialService(db)
    fin.record_product_sold(1, 450.0, "Basic300", 1)

    SimulationService(db).reset_simulation()

    cfg = ConfigService(db).serialize_config()
    assert cfg["total_revenue"] == 0.0
    assert cfg["total_costs"] == 0.0


# ── sales order delivery pipeline ────────────────────────────────────────────

def test_sales_order_product_sold_uses_wholesale_price(db: Session) -> None:
    """DELIVERED SalesOrder records PRODUCT_SOLD at the wholesale price."""
    _seed_bom_and_prices(db)

    svc = SalesOrderService(db)
    order = svc.create_from_retailer("PrinterWorld", "Basic300", 2)
    db.commit()

    result = svc.release_to_production(order.id)
    db.commit()

    # Force MO to COMPLETED so the sales order can progress.
    mfg = db.query(ManufacturingOrder).filter_by(id=result["mfg_order_id"]).one()
    mfg.status = OrderStatus.COMPLETED
    db.commit()

    svc.progress_sales_orders(sim_day=2)   # CONFIRMED → IN_PROGRESS
    db.commit()
    svc.progress_sales_orders(sim_day=3)   # IN_PROGRESS → SHIPPED
    db.commit()
    svc.progress_sales_orders(sim_day=4)   # SHIPPED → DELIVERED
    db.commit()

    txns = db.query(FinancialTransaction).filter_by(
        transaction_type=FinancialTransactionType.PRODUCT_SOLD
    ).all()
    assert len(txns) == 1
    # 2 units × £450
    assert txns[0].amount == Decimal("900.00")


def test_sales_order_delivery_updates_config_revenue(db: Session) -> None:
    """total_revenue in SimulationConfig increases when SalesOrder is delivered."""
    _seed_bom_and_prices(db)

    svc = SalesOrderService(db)
    order = svc.create_from_retailer("PrinterWorld", "Elite700", 1)
    db.commit()

    result = svc.release_to_production(order.id)
    db.commit()
    mfg = db.query(ManufacturingOrder).filter_by(id=result["mfg_order_id"]).one()
    mfg.status = OrderStatus.COMPLETED
    db.commit()

    for day in (2, 3, 4):
        svc.progress_sales_orders(sim_day=day)
        db.commit()

    cfg = ConfigService(db).serialize_config()
    assert cfg["total_revenue"] == 1400.0


# ── retailer schema: external_order_id is str ─────────────────────────────────

def test_sales_order_id_is_uuid_string(db: Session) -> None:
    """SalesOrder.id is a UUID string, not an integer."""
    _seed_bom_and_prices(db)
    svc = SalesOrderService(db)
    order = svc.create_from_retailer("PrinterWorld", "Basic300", 1)
    db.commit()

    wire = svc.serialize_order(order)
    # id must be a non-empty string (UUID format)
    assert isinstance(wire["id"], str)
    assert len(wire["id"]) == 36
    assert wire["id"].count("-") == 4
