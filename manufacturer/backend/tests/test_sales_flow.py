"""M3 gate tests for the manufacturer's wholesale sales API.

Covers the scenario required by docs/PRD-week7.md §12 M3:
  A retailer places a purchase order, and after enough day advances
  the sales order transitions from PENDING to DELIVERED.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]

from app.api.routes.sales import router as sales_router  # noqa: E402
from app.models.models import (  # noqa: E402
    Product,
    ProductType,
    SimulationConfig,
    WholesalePrice,
)
from app.services.sales_service import SalesService  # noqa: E402
from app.utils.database import Base, get_db  # noqa: E402


# ── shared test helpers ───────────────────────────────────────────────────────


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return Local()


def _seed_db(session):
    """Seed a Basic300 product with a wholesale price of $750 / 3-day lead."""
    config = SimulationConfig(
        id=1,
        warehouse_capacity=2200,
        daily_assembly_hours=8.0,
        assembly_lines=1,
        workers_per_line=1,
        shift_hours=8.0,
        demand_distribution_mean=5.0,
        demand_distribution_variance=2.0,
        sim_date=date(2026, 5, 11),
    )
    session.add(config)

    printer = Product(name="Basic300", type=ProductType.PRINTER, assembly_hours=2.0)
    session.add(printer)
    session.flush()

    session.add(
        WholesalePrice(product_id=printer.id, price=Decimal("750.00"), lead_time_days=3)
    )
    session.commit()
    return printer


# ── service-layer tests ───────────────────────────────────────────────────────


def test_create_sales_order_sets_expected_delivery_day():
    """Sales order placed on day 0 with 3-day lead → expected_delivery_day = 3."""
    session = _make_session()
    _seed_db(session)

    svc = SalesService(session)
    order = svc.create_order("Basic300", 5, "PrinterWorld")
    session.commit()

    assert order.placed_day == 0
    assert order.expected_delivery_day == 3
    assert order.status.value == "PENDING"
    assert order.quantity == 5
    assert float(order.unit_price) == 750.0
    assert float(order.total_price) == 3750.0


def test_sales_order_delivered_after_enough_day_advances():
    """After 3 day advances the PENDING order transitions to DELIVERED."""
    session = _make_session()
    _seed_db(session)

    svc = SalesService(session)
    order = svc.create_order("Basic300", 5, "PrinterWorld")
    session.commit()
    order_id = order.id

    for _ in range(3):
        new_day = svc.increment_day()
        svc.process_deliveries(new_day)
    session.commit()

    session.refresh(order)
    assert order.status.value == "DELIVERED"
    assert order.delivered_day == 3


def test_sales_order_not_delivered_before_lead_time():
    """After only 2 advances (< 3-day lead) order remains PENDING."""
    session = _make_session()
    _seed_db(session)

    svc = SalesService(session)
    order = svc.create_order("Basic300", 2, "RetailShop")
    session.commit()

    for _ in range(2):
        new_day = svc.increment_day()
        svc.process_deliveries(new_day)
    session.commit()

    session.refresh(order)
    assert order.status.value == "PENDING"


# ── HTTP route tests ──────────────────────────────────────────────────────────


def _make_test_client():
    session = _make_session()
    _seed_db(session)

    test_app = FastAPI()
    test_app.include_router(sales_router, prefix="/api/sales")

    def override_get_db():
        try:
            yield session
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    return TestClient(test_app), session


def test_post_sales_order_returns_201():
    client, _ = _make_test_client()
    resp = client.post(
        "/api/sales/orders",
        json={"model_name": "Basic300", "quantity": 5, "buyer_name": "PrinterWorld"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["model_name"] == "Basic300"
    assert data["quantity"] == 5
    assert data["status"] == "PENDING"
    assert data["expected_delivery_day"] == 3


def test_get_sales_order_returns_200():
    client, _ = _make_test_client()
    post_resp = client.post(
        "/api/sales/orders",
        json={"model_name": "Basic300", "quantity": 1, "buyer_name": "Buyer"},
    )
    order_id = post_resp.json()["id"]
    get_resp = client.get(f"/api/sales/orders/{order_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == order_id


def test_get_nonexistent_sales_order_returns_404():
    client, _ = _make_test_client()
    resp = client.get("/api/sales/orders/9999")
    assert resp.status_code == 404


def test_list_wholesale_prices():
    client, _ = _make_test_client()
    resp = client.get("/api/sales/prices")
    assert resp.status_code == 200
    prices = resp.json()
    assert any(p["model_name"] == "Basic300" for p in prices)


def test_set_wholesale_price():
    client, _ = _make_test_client()
    resp = client.put(
        "/api/sales/prices/Basic300",
        json={"price": 800.0, "lead_time_days": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["price"] == 800.0
    assert data["lead_time_days"] == 2
