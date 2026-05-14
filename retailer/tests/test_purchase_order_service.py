"""Unit tests for `PurchaseOrderService`.

Uses `httpx.MockTransport` to fake the manufacturer's REST surface
without booting a real server. We assert both directions: the request
the retailer sends, and the local DB rows + events it produces from
the manufacturer's response.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest
from sqlalchemy.orm import Session

from app.models.models import EventType, PurchaseOrderStatus
from app.services.event_service import EventService
from app.services.manufacturer_client import ManufacturerClient, ManufacturerError
from app.services.purchase_order_service import PurchaseOrderService
from app.services.stock_service import StockService


def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> ManufacturerClient:
    transport = httpx.MockTransport(handler)
    return ManufacturerClient("http://manufacturer:8002", transport=transport)


def test_place_purchase_order_records_local_row_and_event(seeded_session: Session) -> None:
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/sales/orders"
        captured.append(dict(request.headers))
        return httpx.Response(
            201,
            json={
                "schema_version": 1,
                "order": {
                    "id": 42,
                    "retailer": "PrinterWorld",
                    "model": "Basic300",
                    "quantity": 4,
                    "unit_price": "450.00",
                    "total_price": "1800.00",
                    "placed_day": 1,
                    "expected_ship_day": 3,
                    "status": "PENDING",
                    "status_reason": None,
                },
            },
        )

    service = PurchaseOrderService(seeded_session, _make_client(handler))

    order = service.place_purchase_order(
        retailer_name="PrinterWorld",
        manufacturer_name="Factory",
        product_name="Basic300",
        quantity=4,
        sim_day=1,
    )
    seeded_session.commit()

    assert order.external_order_id == 42
    assert order.status == PurchaseOrderStatus.PENDING
    assert order.expected_delivery_day == 3
    assert str(order.unit_price) == "450.00"
    assert str(order.total_price) == "1800.00"
    assert len(captured) == 1

    placed_events = EventService(seeded_session).list(
        event_type=EventType.PURCHASE_ORDER_PLACED
    )
    assert len(placed_events) == 1


def test_place_purchase_order_records_rejection(seeded_session: Session) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={
                "schema_version": 1,
                "order": {
                    "id": 9,
                    "retailer": "PrinterWorld",
                    "model": "Basic300",
                    "quantity": 4,
                    "unit_price": "450.00",
                    "total_price": "1800.00",
                    "placed_day": 1,
                    "expected_ship_day": None,
                    "status": "REJECTED",
                    "status_reason": "no capacity",
                },
            },
        )

    service = PurchaseOrderService(seeded_session, _make_client(handler))

    order = service.place_purchase_order(
        retailer_name="PrinterWorld",
        manufacturer_name="Factory",
        product_name="Basic300",
        quantity=4,
        sim_day=1,
    )
    seeded_session.commit()

    assert order.status == PurchaseOrderStatus.REJECTED
    assert order.status_reason == "no capacity"

    rejected_events = EventService(seeded_session).list(
        event_type=EventType.PURCHASE_ORDER_REJECTED
    )
    assert len(rejected_events) == 1


def test_place_purchase_order_raises_on_http_error(seeded_session: Session) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    service = PurchaseOrderService(seeded_session, _make_client(handler))

    with pytest.raises(ManufacturerError, match="rejected"):
        service.place_purchase_order(
            retailer_name="PrinterWorld",
            manufacturer_name="Factory",
            product_name="Basic300",
            quantity=4,
            sim_day=1,
        )


def test_poll_pending_orders_delivers_into_stock(seeded_session: Session) -> None:
    # Phase 1: place an order that the manufacturer accepts.
    def place_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={
                "schema_version": 1,
                "order": {
                    "id": 100,
                    "retailer": "PrinterWorld",
                    "model": "Basic300",
                    "quantity": 5,
                    "unit_price": "450.00",
                    "total_price": "2250.00",
                    "placed_day": 1,
                    "expected_ship_day": 3,
                    "status": "PENDING",
                    "status_reason": None,
                },
            },
        )

    service = PurchaseOrderService(seeded_session, _make_client(place_handler))
    order = service.place_purchase_order(
        retailer_name="PrinterWorld",
        manufacturer_name="Factory",
        product_name="Basic300",
        quantity=5,
        sim_day=1,
    )
    seeded_session.commit()
    initial_stock = StockService(seeded_session).get_quantity("Basic300")
    assert order.external_order_id == 100

    # Phase 2: swap the client for one that reports DELIVERED.
    def poll_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/sales/orders/100"
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "order": {
                    "id": 100,
                    "retailer": "PrinterWorld",
                    "model": "Basic300",
                    "quantity": 5,
                    "unit_price": "450.00",
                    "total_price": "2250.00",
                    "placed_day": 1,
                    "expected_ship_day": 3,
                    "shipped_day": 3,
                    "delivered_day": 4,
                    "status": "DELIVERED",
                    "status_reason": None,
                },
            },
        )

    delivery_service = PurchaseOrderService(seeded_session, _make_client(poll_handler))
    results = delivery_service.poll_pending_orders(sim_day=4)
    seeded_session.commit()

    assert results == [
        {
            "order_id": order.id,
            "external_order_id": 100,
            "status": "DELIVERED",
            "quantity": 5,
        }
    ]

    seeded_session.refresh(order)
    assert order.status == PurchaseOrderStatus.DELIVERED
    assert order.delivered_day == 4
    assert StockService(seeded_session).get_quantity("Basic300") == initial_stock + 5

    delivered_events = EventService(seeded_session).list(
        event_type=EventType.PURCHASE_ORDER_DELIVERED
    )
    assert len(delivered_events) == 1


def test_poll_pending_orders_keeps_pending_on_intermediate_status(
    seeded_session: Session,
) -> None:
    def place_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={
                "schema_version": 1,
                "order": {
                    "id": 200,
                    "retailer": "PrinterWorld",
                    "model": "Pro450",
                    "quantity": 1,
                    "unit_price": "800.00",
                    "total_price": "800.00",
                    "placed_day": 1,
                    "expected_ship_day": 4,
                    "status": "PENDING",
                    "status_reason": None,
                },
            },
        )

    PurchaseOrderService(
        seeded_session, _make_client(place_handler)
    ).place_purchase_order(
        retailer_name="PrinterWorld",
        manufacturer_name="Factory",
        product_name="Pro450",
        quantity=1,
        sim_day=1,
    )
    seeded_session.commit()

    def poll_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "order": {
                    "id": 200,
                    "retailer": "PrinterWorld",
                    "model": "Pro450",
                    "quantity": 1,
                    "unit_price": "800.00",
                    "total_price": "800.00",
                    "placed_day": 1,
                    "expected_ship_day": 4,
                    "status": "IN_PROGRESS",
                    "status_reason": None,
                },
            },
        )

    service = PurchaseOrderService(seeded_session, _make_client(poll_handler))
    results = service.poll_pending_orders(sim_day=2)
    seeded_session.commit()

    assert results[0]["status"] == "IN_PROGRESS"
    assert (
        service.list_orders(status=PurchaseOrderStatus.PENDING)[0].status
        == PurchaseOrderStatus.PENDING
    )
