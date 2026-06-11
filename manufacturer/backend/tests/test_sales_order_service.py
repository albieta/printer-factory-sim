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
    SalesOrder,  # noqa: F401
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


# ── progress_sales_orders 3-day progression tests ────────────────────────────


def _make_completed_mfg_order(session: object, product_id: str, quantity: int, sim_date: date) -> ManufacturingOrder:
    """Helper: create a ManufacturingOrder already in COMPLETED state."""
    mfg = ManufacturingOrder(
        product_id=product_id,
        quantity=quantity,
        status=OrderStatus.COMPLETED,
        created_date=sim_date,
        released_date=sim_date,
        completed_date=sim_date,
        reference_code=f"MO-TEST-{quantity}",
    )
    session.add(mfg)  # type: ignore[arg-type]
    session.flush()  # type: ignore[union-attr]
    return mfg


def test_progress_confirmed_to_in_progress_when_mo_completed(seeded):
    """CONFIRMED SO with a COMPLETED linked MO transitions to IN_PROGRESS."""
    svc = SalesOrderService(seeded)
    order = svc.create_from_retailer("PrinterWorld", "Elite700", 2)
    seeded.commit()

    result = svc.release_to_production(order.id)
    seeded.commit()
    mfg_id = result["mfg_order_id"]

    # Manually complete the linked ManufacturingOrder.
    mfg = seeded.query(ManufacturingOrder).filter_by(id=mfg_id).one()
    mfg.status = OrderStatus.COMPLETED
    seeded.commit()

    counts = svc.progress_sales_orders(sim_day=1)
    seeded.commit()

    assert counts["in_progress"] == 1
    assert counts["shipped"] == 0
    seeded.refresh(order)
    assert order.status == SalesOrderStatus.IN_PROGRESS
    assert order.in_progress_day == 1


def test_progress_confirmed_stays_when_mo_not_completed(seeded):
    """CONFIRMED SO with a RELEASED linked MO stays CONFIRMED."""
    svc = SalesOrderService(seeded)
    order = svc.create_from_retailer("PrinterWorld", "Elite700", 2)
    seeded.commit()
    svc.release_to_production(order.id)
    seeded.commit()

    counts = svc.progress_sales_orders(sim_day=1)
    seeded.commit()

    assert counts["in_progress"] == 0
    seeded.refresh(order)
    assert order.status == SalesOrderStatus.CONFIRMED


def test_progress_in_progress_to_shipped(seeded):
    """IN_PROGRESS SO whose in_progress_day < sim_day transitions to SHIPPED."""
    svc = SalesOrderService(seeded)
    order = svc.create_from_retailer("PrinterWorld", "Basic300", 1)
    seeded.commit()
    svc.release_to_production(order.id)
    seeded.commit()

    mfg = seeded.query(ManufacturingOrder).filter_by(id=order.linked_mfg_order_id).one()
    mfg.status = OrderStatus.COMPLETED
    seeded.commit()

    # Day 1: CONFIRMED → IN_PROGRESS
    svc.progress_sales_orders(sim_day=1)
    seeded.commit()

    # Day 2: IN_PROGRESS → SHIPPED (in_progress_day=1 < 2)
    counts = svc.progress_sales_orders(sim_day=2)
    seeded.commit()

    assert counts["shipped"] == 1
    seeded.refresh(order)
    assert order.status == SalesOrderStatus.SHIPPED
    assert order.shipped_day == 2


def test_progress_shipped_to_delivered(seeded):
    """SHIPPED SO whose shipped_day < sim_day transitions to DELIVERED."""
    svc = SalesOrderService(seeded)
    order = svc.create_from_retailer("PrinterWorld", "Elite700", 3)
    seeded.commit()
    svc.release_to_production(order.id)
    seeded.commit()

    mfg = seeded.query(ManufacturingOrder).filter_by(id=order.linked_mfg_order_id).one()
    mfg.status = OrderStatus.COMPLETED
    seeded.commit()

    svc.progress_sales_orders(sim_day=1)  # → IN_PROGRESS
    seeded.commit()
    svc.progress_sales_orders(sim_day=2)  # → SHIPPED
    seeded.commit()

    counts = svc.progress_sales_orders(sim_day=3)  # → DELIVERED
    seeded.commit()

    assert counts["delivered"] == 1
    seeded.refresh(order)
    assert order.status == SalesOrderStatus.DELIVERED
    assert order.delivered_day == 3


def test_full_3_day_progression(seeded):
    """End-to-end: order placed day 0, progresses through all states by day 3."""
    svc = SalesOrderService(seeded)
    order = svc.create_from_retailer("BestPrinters", "Elite700", 5)
    seeded.commit()
    assert order.status == SalesOrderStatus.PENDING

    result = svc.release_to_production(order.id)
    seeded.commit()
    assert result["success"] is True
    seeded.refresh(order)
    assert order.status == SalesOrderStatus.CONFIRMED

    mfg = seeded.query(ManufacturingOrder).filter_by(id=order.linked_mfg_order_id).one()
    mfg.status = OrderStatus.COMPLETED
    seeded.commit()

    # Day 1: CONFIRMED → IN_PROGRESS
    counts1 = svc.progress_sales_orders(sim_day=1)
    seeded.commit()
    assert counts1["in_progress"] == 1
    seeded.refresh(order)
    assert order.status == SalesOrderStatus.IN_PROGRESS

    # Day 2: IN_PROGRESS → SHIPPED
    counts2 = svc.progress_sales_orders(sim_day=2)
    seeded.commit()
    assert counts2["shipped"] == 1
    seeded.refresh(order)
    assert order.status == SalesOrderStatus.SHIPPED

    # Day 3: SHIPPED → DELIVERED
    counts3 = svc.progress_sales_orders(sim_day=3)
    seeded.commit()
    assert counts3["delivered"] == 1
    seeded.refresh(order)
    assert order.status == SalesOrderStatus.DELIVERED
    assert order.delivered_day == 3


def test_progress_emits_delivered_event(seeded):
    """SALES_ORDER_DELIVERED event is emitted when SO reaches DELIVERED."""
    svc = SalesOrderService(seeded)
    order = svc.create_from_retailer("PrinterWorld", "Basic300", 2)
    seeded.commit()
    svc.release_to_production(order.id)
    seeded.commit()

    mfg = seeded.query(ManufacturingOrder).filter_by(id=order.linked_mfg_order_id).one()
    mfg.status = OrderStatus.COMPLETED
    seeded.commit()

    svc.progress_sales_orders(sim_day=1)
    seeded.commit()
    svc.progress_sales_orders(sim_day=2)
    seeded.commit()
    svc.progress_sales_orders(sim_day=3)
    seeded.commit()

    delivered_events = seeded.query(Event).filter_by(event_type=EventType.SALES_ORDER_DELIVERED).all()
    assert len(delivered_events) == 1
    assert delivered_events[0].details["order_id"] == order.id


def test_progress_no_effect_on_pending_orders(seeded):
    """PENDING orders (not yet released) are unaffected by progress_sales_orders."""
    svc = SalesOrderService(seeded)
    order = svc.create_from_retailer("PrinterWorld", "Elite700", 1)
    seeded.commit()

    counts = svc.progress_sales_orders(sim_day=5)
    seeded.commit()

    assert counts == {"in_progress": 0, "shipped": 0, "delivered": 0}
    seeded.refresh(order)
    assert order.status == SalesOrderStatus.PENDING


def test_multiple_orders_progress_independently(seeded):
    """Two orders at different stages each advance one step per call."""
    svc = SalesOrderService(seeded)
    o1 = svc.create_from_retailer("A", "Elite700", 1)
    o2 = svc.create_from_retailer("B", "Basic300", 1)
    seeded.commit()

    svc.release_to_production(o1.id)
    svc.release_to_production(o2.id)
    seeded.commit()

    # Complete only o1's linked MO.
    mfg1 = seeded.query(ManufacturingOrder).filter_by(id=o1.linked_mfg_order_id).one()
    mfg1.status = OrderStatus.COMPLETED
    seeded.commit()

    counts = svc.progress_sales_orders(sim_day=1)
    seeded.commit()

    # Only o1 should have advanced; o2's MO is still RELEASED.
    assert counts["in_progress"] == 1
    seeded.refresh(o1)
    seeded.refresh(o2)
    assert o1.status == SalesOrderStatus.IN_PROGRESS
    assert o2.status == SalesOrderStatus.CONFIRMED
