"""Unit tests for `DayService.advance_day`.

Verifies the three-step ordering: poll → backorder sweep → increment.
A delivery on day N must be able to satisfy a customer order
backordered on day N-1 in the same tick.
"""

from __future__ import annotations

from typing import Callable

import httpx
from sqlalchemy.orm import Session

from app.models.models import CustomerOrderStatus, EventType, PurchaseOrderStatus
from app.services.customer_order_service import CustomerOrderService
from app.services.day_service import DayService
from app.services.event_service import EventService
from app.services.manufacturer_client import ManufacturerClient
from app.services.purchase_order_service import PurchaseOrderService
from app.services.sim_state_service import SimStateService
from app.services.stock_service import StockService


def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> ManufacturerClient:
    return ManufacturerClient("http://manufacturer:8002", transport=httpx.MockTransport(handler))


def test_advance_day_delivery_satisfies_existing_backorder(seeded_session: Session) -> None:
    # Day 1: customer orders 3 × Elite700, only 1 in stock -> backorder.
    co_service = CustomerOrderService(seeded_session)
    backorder_id = co_service.place_order("alice", "Elite700", 3, sim_day=1).id
    seeded_session.commit()

    # Day 1: retailer places a PO for 5 Elite700 with the manufacturer.
    def place_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={
                "schema_version": 1,
                "order": {
                    "id": 555,
                    "retailer": "PrinterWorld",
                    "model": "Elite700",
                    "quantity": 5,
                    "unit_price": "1400.00",
                    "total_price": "7000.00",
                    "placed_day": 1,
                    "expected_ship_day": 2,
                    "status": "PENDING",
                    "status_reason": None,
                },
            },
        )

    PurchaseOrderService(seeded_session, _make_client(place_handler)).place_purchase_order(
        retailer_name="PrinterWorld",
        manufacturer_name="Factory",
        product_name="Elite700",
        quantity=5,
        sim_day=1,
    )
    seeded_session.commit()

    # Day 2 advance: manufacturer reports DELIVERED. Day service must
    # add 5 to stock, then satisfy the backorder, then increment.
    def poll_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "order": {
                    "id": 555,
                    "retailer": "PrinterWorld",
                    "model": "Elite700",
                    "quantity": 5,
                    "unit_price": "1400.00",
                    "total_price": "7000.00",
                    "placed_day": 1,
                    "expected_ship_day": 2,
                    "shipped_day": 2,
                    "delivered_day": 2,
                    "status": "DELIVERED",
                    "status_reason": None,
                },
            },
        )

    # Day counter is at 0 from the seed; bump to 1 so the test mirrors
    # a real day-2 advance.
    SimStateService(seeded_session).set_current_day(1)
    seeded_session.commit()

    summary = DayService(seeded_session, _make_client(poll_handler)).advance_day()

    assert summary["previous_day"] == 1
    assert summary["current_day"] == 2
    assert summary["purchase_orders_delivered"] == 1
    assert summary["backorders_fulfilled"] == 1

    refreshed = co_service.get_order(backorder_id)
    assert refreshed is not None
    assert refreshed.status == CustomerOrderStatus.FULFILLED
    assert refreshed.fulfilled_day == 1  # day before the increment

    # Stock: 1 initial + 5 delivered - 3 fulfilled = 3
    assert StockService(seeded_session).get_quantity("Elite700") == 3
    assert SimStateService(seeded_session).get_current_day() == 2

    day_events = EventService(seeded_session).list(event_type=EventType.DAY_ADVANCED)
    assert len(day_events) == 1


def test_advance_day_with_no_activity_still_increments(seeded_session: Session) -> None:
    def handler(_: httpx.Request) -> httpx.Response:  # never called
        raise AssertionError("no HTTP calls expected when there are no pending POs")

    summary = DayService(seeded_session, _make_client(handler)).advance_day()

    assert summary["previous_day"] == 0
    assert summary["current_day"] == 1
    assert summary["purchase_orders_delivered"] == 0
    assert summary["backorders_fulfilled"] == 0
    assert summary["po_poll_results"] == []

    pending = (
        PurchaseOrderService(seeded_session, _make_client(handler))
        .list_orders(status=PurchaseOrderStatus.PENDING)
    )
    assert pending == []
