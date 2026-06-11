"""Purchase orders the retailer places with the manufacturer.

This service handles the *outbound* side of the Week 7 retailer →
manufacturer integration. The data model mirrors the Week 6 manufacturer
→ provider integration: a local `PurchaseOrder` row carries an
`external_order_id` pointing at the manufacturer's `SalesOrder`, and the
retailer polls the manufacturer for status updates on day advance.

The lifecycle is collapsed to `PENDING → DELIVERED | REJECTED` from the
retailer's point of view; the manufacturer owns the
`CONFIRMED / IN_PROGRESS / SHIPPED` intermediate states.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.models import (
    EventType,
    PurchaseOrder,
    PurchaseOrderStatus,
)
from app.services.event_service import EventService
from app.services.manufacturer_client import ManufacturerClient, ManufacturerError
from app.services.stock_service import StockService


# Manufacturer-side `SalesOrder.status` values that mean "the goods have
# arrived". The retailer only acts on `DELIVERED`; any prior status
# keeps the local row in `PENDING`.
DELIVERED_STATUS = "DELIVERED"
REJECTED_STATUS = "REJECTED"
CANCELLED_STATUS = "CANCELLED"


class PurchaseOrderService:
    """Place and track POs the retailer has placed with the manufacturer."""

    def __init__(self, db: Session, manufacturer_client: ManufacturerClient) -> None:
        self.db = db
        self.client = manufacturer_client
        self.events = EventService(db)
        self.stock = StockService(db)

    def list_orders(
        self, status: Optional[PurchaseOrderStatus] = None
    ) -> list[PurchaseOrder]:
        query = self.db.query(PurchaseOrder)
        if status is not None:
            query = query.filter(PurchaseOrder.status == status)
        return query.order_by(PurchaseOrder.id.desc()).all()

    def get_order(self, order_id: int) -> Optional[PurchaseOrder]:
        return self.db.query(PurchaseOrder).filter_by(id=order_id).one_or_none()

    def place_purchase_order(
        self,
        retailer_name: str,
        manufacturer_name: str,
        product_name: str,
        quantity: int,
        sim_day: int,
    ) -> PurchaseOrder:
        """Send a new PO to the manufacturer and record it locally.

        The manufacturer's response carries the unit price and the
        expected delivery day; we snapshot both. On a manufacturer
        rejection we still persist the local row so the audit trail
        captures the attempt.
        """

        if quantity <= 0:
            raise ValueError("quantity must be positive")

        order_payload = self.client.create_sales_order(
            retailer_name=retailer_name,
            product_name=product_name,
            quantity=quantity,
        )

        external_status = str(order_payload.get("status", "PENDING")).upper()
        unit_price = Decimal(str(order_payload.get("unit_price", "0")))
        total_price = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"))
        expected_delivery = order_payload.get("expected_ship_day")
        if expected_delivery is None:
            expected_delivery = order_payload.get("expected_delivery_day")

        local_status = (
            PurchaseOrderStatus.REJECTED
            if external_status == REJECTED_STATUS
            else PurchaseOrderStatus.PENDING
        )

        order = PurchaseOrder(
            manufacturer_name=manufacturer_name,
            product_name=product_name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            placed_day=sim_day,
            expected_delivery_day=int(expected_delivery) if expected_delivery is not None else None,
            status=local_status,
            status_reason=order_payload.get("status_reason"),
            external_order_id=order_payload.get("id"),
        )
        self.db.add(order)
        self.db.flush()

        self.events.record(
            EventType.PURCHASE_ORDER_PLACED,
            sim_day,
            entity_type="purchase_order",
            entity_id=order.id,
            details={
                "manufacturer_name": manufacturer_name,
                "product_name": product_name,
                "quantity": quantity,
                "unit_price": str(unit_price),
                "total_price": str(total_price),
                "expected_delivery_day": order.expected_delivery_day,
                "external_order_id": order.external_order_id,
                "external_status": external_status,
            },
        )
        if local_status == PurchaseOrderStatus.REJECTED:
            self.events.record(
                EventType.PURCHASE_ORDER_REJECTED,
                sim_day,
                entity_type="purchase_order",
                entity_id=order.id,
                details={
                    "external_order_id": order.external_order_id,
                    "reason": order.status_reason,
                },
            )

        self.db.flush()
        return order

    def poll_pending_orders(self, sim_day: int) -> list[dict[str, Any]]:
        """Poll the manufacturer for each pending PO; receive on delivery.

        For each pending order with an `external_order_id`, ask the
        manufacturer for the latest status. On `DELIVERED`, increment
        stock, mark the local row delivered, and record events. On
        `REJECTED` or `CANCELLED`, transition the local row to a
        terminal state without touching stock. Other statuses leave
        the local row pending.

        Returns a list of per-order result dicts for the caller's logs.
        """

        pending = (
            self.db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.status == PurchaseOrderStatus.PENDING,
                PurchaseOrder.external_order_id.is_not(None),
            )
            .order_by(PurchaseOrder.id.asc())
            .all()
        )

        results: list[dict[str, Any]] = []
        for order in pending:
            assert order.external_order_id is not None  # narrowed by the filter above
            try:
                payload = self.client.get_sales_order(order.external_order_id)
            except ManufacturerError as exc:
                results.append(
                    {
                        "order_id": order.id,
                        "external_order_id": order.external_order_id,
                        "status": "POLL_FAILED",
                        "error": str(exc),
                    }
                )
                continue

            status = str(payload.get("status", "PENDING")).upper()
            if status == DELIVERED_STATUS:
                self.stock.add_stock(order.product_name, order.quantity, sim_day)
                order.status = PurchaseOrderStatus.DELIVERED
                order.delivered_day = sim_day
                self.events.record(
                    EventType.PURCHASE_ORDER_DELIVERED,
                    sim_day,
                    entity_type="purchase_order",
                    entity_id=order.id,
                    details={
                        "product_name": order.product_name,
                        "quantity": order.quantity,
                        "external_order_id": order.external_order_id,
                    },
                )
                results.append(
                    {
                        "order_id": order.id,
                        "external_order_id": order.external_order_id,
                        "status": "DELIVERED",
                        "quantity": order.quantity,
                    }
                )
            elif status == REJECTED_STATUS:
                order.status = PurchaseOrderStatus.REJECTED
                order.status_reason = payload.get("status_reason")
                self.events.record(
                    EventType.PURCHASE_ORDER_REJECTED,
                    sim_day,
                    entity_type="purchase_order",
                    entity_id=order.id,
                    details={
                        "external_order_id": order.external_order_id,
                        "reason": order.status_reason,
                    },
                )
                results.append(
                    {
                        "order_id": order.id,
                        "external_order_id": order.external_order_id,
                        "status": "REJECTED",
                    }
                )
            elif status == CANCELLED_STATUS:
                order.status = PurchaseOrderStatus.CANCELLED
                order.status_reason = payload.get("status_reason")
                self.events.record(
                    EventType.PURCHASE_ORDER_CANCELLED,
                    sim_day,
                    entity_type="purchase_order",
                    entity_id=order.id,
                    details={
                        "external_order_id": order.external_order_id,
                        "reason": order.status_reason,
                    },
                )
                results.append(
                    {
                        "order_id": order.id,
                        "external_order_id": order.external_order_id,
                        "status": "CANCELLED",
                    }
                )
            else:
                results.append(
                    {
                        "order_id": order.id,
                        "external_order_id": order.external_order_id,
                        "status": status,
                    }
                )

        self.db.flush()
        return results
