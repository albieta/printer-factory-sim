"""Tests for SalesOrderService and WholesalePriceService.

Uses an in-memory SQLite database seeded with one printer model (Elite700),
its wholesale price, and a minimal SimulationConfig so day=0 is available.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]

import pytest  # noqa: E402

from app.models.models import (  # noqa: E402
    EventType,
    Event,
    ManufacturingOrder,
    OrderStatus,
    Product,
    ProductType,
    SalesOrderStatus,
    SimulationConfig,
    WholesalePrice,
)
from app.services.sales_order_service import SalesOrderService  # noqa: E402
from app.services.wholesale_price_service import WholesalePriceService  # noqa: E402
from app.utils.database import Base  # noqa: E402


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def seeded(session):
    """Seed one printer model, its wholesale price, and sim config."""
    config = SimulationConfig(
        warehouse_capacity=5000,
        assembly_lines=1,
        workers_per_line=1,
        shift_hours=8.0,
        daily_assembly_hours=8.0,
        demand_distribution_mean=5.0,
        demand_distribution_variance=2.0,
        sim_date=date(2026, 5, 14),
        sim_day=0,
    )
    session.add(config)

    elite = Product(name="Elite700", type=ProductType.PRINTER, assembly_hours=6.0)
    basic = Product(name="Basic300", type=ProductType.PRINTER, assembly_hours=2.0)
    session.add_all([elite, basic])
    session.flush()

    session.add(WholesalePrice(product_id=elite.id, price=Decimal("1400.00")))
    session.add(WholesalePrice(product_id=basic.id, price=Decimal("450.00")))
    session.commit()
    return session


# ── SalesOrderService tests ───────────────────────────────────────────────────

def test_create_from_retailer_returns_pending_order(seeded):
    service = SalesOrderService(seeded)
    order = service.create_from_retailer("PrinterWorld", "Elite700", 3)
    seeded.commit()

    assert order.status == SalesOrderStatus.PENDING
    assert order.retailer_name == "PrinterWorld"
    assert order.quantity == 3
    assert order.unit_price == Decimal("1400.00")
    assert order.total_price == Decimal("4200.00")
    assert order.placed_day == 0
    assert order.expected_ship_day == 3  # placed_day + DEFAULT_LEAD_DAYS
    assert order.reference_code is not None
    assert order.reference_code.startswith("SO-")


def test_create_from_retailer_emits_event(seeded):
    SalesOrderService(seeded).create_from_retailer("PrinterWorld", "Elite700", 2)
    seeded.commit()

    events = seeded.query(Event).filter_by(event_type=EventType.SALES_ORDER_PLACED).all()
    assert len(events) == 1
    assert events[0].details["retailer_name"] == "PrinterWorld"
    assert events[0].details["quantity"] == 2


def test_create_from_retailer_rejects_unknown_model(seeded):
    with pytest.raises(ValueError, match="No printer model"):
        SalesOrderService(seeded).create_from_retailer("PrinterWorld", "Mystery9000", 1)


def test_create_from_retailer_rejects_zero_quantity(seeded):
    with pytest.raises(ValueError, match="positive"):
        SalesOrderService(seeded).create_from_retailer("PrinterWorld", "Elite700", 0)


def test_list_orders_returns_all_by_default(seeded):
    svc = SalesOrderService(seeded)
    svc.create_from_retailer("A", "Elite700", 1)
    svc.create_from_retailer("B", "Basic300", 2)
    seeded.commit()

    orders = svc.list_orders()
    assert len(orders) == 2


def test_list_orders_filters_by_status(seeded):
    svc = SalesOrderService(seeded)
    o1 = svc.create_from_retailer("A", "Elite700", 1)
    seeded.commit()

    # Release one, leave the other pending.
    svc.release_to_production(o1.id)
    seeded.commit()

    pending = svc.list_orders(status=SalesOrderStatus.PENDING)
    confirmed = svc.list_orders(status=SalesOrderStatus.CONFIRMED)
    assert pending == []
    assert len(confirmed) == 1


def test_get_order_returns_none_for_missing(seeded):
    result = SalesOrderService(seeded).get_order("nonexistent-id")
    assert result is None


def test_release_to_production_creates_mfg_order(seeded):
    svc = SalesOrderService(seeded)
    order = svc.create_from_retailer("PrinterWorld", "Elite700", 5)
    seeded.commit()

    result = svc.release_to_production(order.id)
    seeded.commit()

    assert result["success"] is True
    seeded.refresh(order)
    assert order.status == SalesOrderStatus.CONFIRMED

    mfg_orders = seeded.query(ManufacturingOrder).all()
    assert len(mfg_orders) == 1
    assert mfg_orders[0].quantity == 5
    assert mfg_orders[0].status == OrderStatus.RELEASED

    events = seeded.query(Event).filter_by(event_type=EventType.SALES_ORDER_RELEASED).all()
    assert len(events) == 1


def test_release_to_production_rejects_non_pending(seeded):
    svc = SalesOrderService(seeded)
    order = svc.create_from_retailer("PrinterWorld", "Basic300", 1)
    seeded.commit()
    svc.release_to_production(order.id)
    seeded.commit()

    # Second release must fail.
    result = svc.release_to_production(order.id)
    assert result["success"] is False
    assert "PENDING" in result["error"]


def test_release_to_production_rejects_unknown_id(seeded):
    result = SalesOrderService(seeded).release_to_production("bad-id")
    assert result["success"] is False
    assert "not found" in result["error"]


def test_serialize_order_matches_retailer_wire_format(seeded):
    svc = SalesOrderService(seeded)
    order = svc.create_from_retailer("PrinterWorld", "Elite700", 2)
    seeded.commit()

    wire = svc.serialize_order(order)
    assert wire["retailer"] == "PrinterWorld"
    assert wire["model"] == "Elite700"
    assert wire["quantity"] == 2
    assert wire["status"] == "PENDING"
    assert wire["placed_day"] == 0
    assert "unit_price" in wire
    assert "total_price" in wire


def test_get_production_status_only_returns_active(seeded):
    svc = SalesOrderService(seeded)
    o1 = svc.create_from_retailer("A", "Elite700", 1)
    o2 = svc.create_from_retailer("B", "Basic300", 1)
    seeded.commit()

    # Cancel o2 manually to simulate a terminal state.
    o2.status = SalesOrderStatus.DELIVERED
    seeded.commit()

    active = svc.get_production_status()
    assert len(active) == 1
    assert active[0]["id"] == o1.id


# ── WholesalePriceService tests ───────────────────────────────────────────────

def test_list_prices_returns_seeded_values(seeded):
    prices = WholesalePriceService(seeded).list_prices()
    assert prices["Basic300"] == Decimal("450.00")
    assert prices["Elite700"] == Decimal("1400.00")


def test_set_price_updates_existing_row(seeded):
    svc = WholesalePriceService(seeded)
    result = svc.set_price("Elite700", Decimal("1500.00"))
    seeded.commit()

    assert result["price"] == "1500.00"
    assert result["previous_price"] == "1400.00"
    assert svc.get_price("Elite700") == Decimal("1500.00")


def test_set_price_rejects_zero(seeded):
    with pytest.raises(ValueError, match="positive"):
        WholesalePriceService(seeded).set_price("Elite700", Decimal("0"))


def test_set_price_rejects_unknown_model(seeded):
    with pytest.raises(ValueError, match="No printer model"):
        WholesalePriceService(seeded).set_price("Mystery9000", Decimal("100"))


def test_set_price_emits_event(seeded):
    WholesalePriceService(seeded).set_price("Basic300", Decimal("500.00"))
    seeded.commit()

    events = seeded.query(Event).filter_by(event_type=EventType.WHOLESALE_PRICE_CHANGED).all()
    assert len(events) == 1
    assert events[0].details["new_price"] == "500.00"


def test_ensure_defaults_seeds_missing_prices(session):
    config = SimulationConfig(
        warehouse_capacity=5000, assembly_lines=1, workers_per_line=1,
        shift_hours=8.0, daily_assembly_hours=8.0,
        demand_distribution_mean=5.0, demand_distribution_variance=2.0,
        sim_date=date(2026, 5, 14), sim_day=0,
    )
    pro = Product(name="Pro450", type=ProductType.PRINTER, assembly_hours=4.0)
    session.add_all([config, pro])
    session.commit()

    WholesalePriceService(session).ensure_defaults()
    session.commit()

    price = WholesalePriceService(session).get_price("Pro450")
    assert price == Decimal("800.00")
