"""M2 gate tests for the retailer's order and day-advance logic.

Covers the three scenarios required by `docs/PRD-week7.md` §12 M2:
  1. Customer order fulfilled from stock.
  2. Customer order backordered when stock is zero.
  3. Day advance with mocked manufacturer delivery auto-fulfils a backorder.

The manufacturer HTTP calls are mocked via `httpx.MockTransport` — the
same pattern used in the manufacturer's own integration smoke tests.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Allow the test to import from the retailer package.
RETAILER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RETAILER_ROOT))

from app.models.models import (  # noqa: E402
    CatalogItem,
    CustomerOrderStatus,
    PurchaseOrder,
    PurchaseOrderStatus,
    SimState,
    Stock,
)
from app.services.day_service import DayService  # noqa: E402
from app.services.order_service import OrderService  # noqa: E402
from app.utils.database import Base, init_db  # noqa: E402


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db() -> Session:  # type: ignore[return]
    """Fresh in-memory SQLite database seeded with one catalog item."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    # Side-effect: register all models with Base.
    from app.models import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Point the module-level engine at this in-memory instance.
    init_db(":memory:")  # ignored — we use our own engine below

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    item = CatalogItem(model_name="Basic300", retail_price=Decimal("999.00"))
    session.add(item)
    session.flush()
    session.add(Stock(catalog_item_id=item.id, quantity=5))
    session.add(SimState(key="current_day", value="1"))
    session.commit()

    yield session  # type: ignore[misc]
    session.close()


def _get_item(db: Session) -> CatalogItem:
    item = db.query(CatalogItem).filter_by(model_name="Basic300").one()
    return item


# ── test 1: fulfilled from stock ──────────────────────────────────────────────


def test_customer_order_fulfilled_from_stock(db: Session) -> None:
    svc = OrderService(db)
    order = svc.place_order("Basic300", 2)

    assert order.status == CustomerOrderStatus.FULFILLED
    assert order.fulfilled_day == 1

    item = _get_item(db)
    stock = db.query(Stock).filter_by(catalog_item_id=item.id).one()
    assert stock.quantity == 3  # 5 − 2


# ── test 2: backordered when stock is zero ────────────────────────────────────


def test_customer_order_backordered_when_no_stock(db: Session) -> None:
    item = _get_item(db)
    stock = db.query(Stock).filter_by(catalog_item_id=item.id).one()
    stock.quantity = 0
    db.commit()

    svc = OrderService(db)
    order = svc.place_order("Basic300", 2)

    assert order.status == CustomerOrderStatus.BACKORDERED
    assert order.fulfilled_day is None


# ── test 3: day advance auto-fulfils a backorder ──────────────────────────────


def test_day_advance_fulfills_backorder_after_delivery(db: Session) -> None:
    item = _get_item(db)

    # Drive stock to zero so the customer order backordered.
    stock_row = db.query(Stock).filter_by(catalog_item_id=item.id).one()
    stock_row.quantity = 0
    db.commit()

    customer_order = OrderService(db).place_order("Basic300", 2)
    assert customer_order.status == CustomerOrderStatus.BACKORDERED

    # Simulate a purchase order already placed with the manufacturer.
    po = PurchaseOrder(
        catalog_item_id=item.id,
        quantity=5,
        unit_price=Decimal("750.00"),
        total_price=Decimal("3750.00"),
        placed_day=1,
        expected_delivery_day=3,
        external_order_id=42,
        status=PurchaseOrderStatus.PENDING,
    )
    db.add(po)
    db.commit()

    # Mock the manufacturer: order 42 is DELIVERED.
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/sales/orders/42":
            return httpx.Response(
                200,
                json={"id": 42, "status": "DELIVERED", "delivered_day": 2},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(_handler)
    day_svc = DayService(db, "http://manufacturer", http_transport=transport)
    result = day_svc.advance()

    assert result.deliveries_received == 1
    assert result.backorders_fulfilled == 1
    assert result.current_day == 2

    db.refresh(customer_order)
    assert customer_order.status == CustomerOrderStatus.FULFILLED
    assert customer_order.fulfilled_day == 2

    # Remaining stock: 5 delivered − 2 consumed by backorder = 3.
    db.refresh(stock_row)
    assert stock_row.quantity == 3
