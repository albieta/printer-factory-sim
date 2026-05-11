"""Purchase order lifecycle for the retailer app.

The retailer places purchase orders with the manufacturer over REST
(same polling pattern that the manufacturer uses against the provider).
An optional `http_transport` parameter lets tests inject a mock without
touching the network.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.models.models import EventType, PurchaseOrder, PurchaseOrderStatus
from app.services.catalog_service import CatalogService
from app.services.event_service import EventService
from app.services.sim_state_service import SimStateService


class PurchaseError(Exception):
    pass


# Statuses the retailer polls the manufacturer for — anything not yet terminal.
_IN_FLIGHT_STATUSES = {
    PurchaseOrderStatus.PENDING,
    PurchaseOrderStatus.CONFIRMED,
    PurchaseOrderStatus.IN_PROGRESS,
    PurchaseOrderStatus.SHIPPED,
}


class PurchaseService:
    def __init__(
        self,
        db: Session,
        manufacturer_url: str,
        http_transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._db = db
        self._manufacturer_url = manufacturer_url.rstrip("/")
        self._transport = http_transport
        self._catalog = CatalogService(db)
        self._events = EventService(db)
        self._sim_state = SimStateService(db)

    def _client(self) -> httpx.Client:
        if self._transport is not None:
            return httpx.Client(transport=self._transport)
        return httpx.Client(timeout=10.0)

    def create(
        self, model_name: str, quantity: int, buyer_name: str
    ) -> PurchaseOrder:
        """POST a purchase order to the manufacturer and persist it locally.

        Raises `httpx.HTTPError` if the manufacturer is unreachable or
        returns a non-2xx response — surfaces the error per CLAUDE.md.
        """
        if quantity <= 0:
            raise PurchaseError("quantity must be positive")

        item = self._catalog.get_by_name(model_name)
        current_day = self._sim_state.get_current_day()

        with self._client() as client:
            resp = client.post(
                f"{self._manufacturer_url}/api/sales/orders",
                json={"buyer_name": buyer_name, "model_name": model_name, "quantity": quantity},
            )
            resp.raise_for_status()
            data = resp.json()

        # Use manufacturer's computed price and delivery day.
        unit_price = Decimal(str(data.get("unit_price", 0)))
        total_price = Decimal(str(data.get("total_price", 0)))
        expected_delivery_day = int(
            data.get("expected_delivery_day", current_day + 2)
        )

        po = PurchaseOrder(
            catalog_item_id=item.id,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            placed_day=current_day,
            expected_delivery_day=expected_delivery_day,
            external_order_id=int(data["id"]),
            status=PurchaseOrderStatus.PENDING,
        )
        self._db.add(po)
        self._db.flush()

        self._events.record(
            EventType.PURCHASE_ORDER_PLACED,
            current_day,
            entity_type="purchase_order",
            entity_id=po.id,
            details={
                "model": model_name,
                "quantity": quantity,
                "external_order_id": po.external_order_id,
                "expected_delivery_day": expected_delivery_day,
            },
        )
        self._db.commit()
        self._db.refresh(po)
        return po

    def list_orders(self) -> list[PurchaseOrder]:
        return (
            self._db.query(PurchaseOrder).order_by(PurchaseOrder.id.desc()).all()
        )

    def get_order(self, order_id: int) -> Optional[PurchaseOrder]:
        return (
            self._db.query(PurchaseOrder).filter_by(id=order_id).one_or_none()
        )

    def poll_deliveries(self, current_day: int) -> list[PurchaseOrder]:
        """Poll the manufacturer for every in-flight purchase order.

        Updates local status to match the manufacturer's reported status.
        Returns the list of orders that transitioned to DELIVERED this call.
        """
        in_flight = (
            self._db.query(PurchaseOrder)
            .filter(PurchaseOrder.status.in_(list(_IN_FLIGHT_STATUSES)))
            .filter(PurchaseOrder.external_order_id.isnot(None))
            .all()
        )

        delivered: list[PurchaseOrder] = []
        with self._client() as client:
            for po in in_flight:
                resp = client.get(
                    f"{self._manufacturer_url}/api/sales/orders/{po.external_order_id}"
                )
                resp.raise_for_status()
                data = resp.json()

                remote_status_str: str = data.get("status", "").upper()
                try:
                    remote_status = PurchaseOrderStatus(remote_status_str)
                except ValueError:
                    continue  # unknown status — skip without crashing

                if remote_status == po.status:
                    continue

                po.status = remote_status

                if remote_status == PurchaseOrderStatus.DELIVERED:
                    po.delivered_day = int(data.get("delivered_day") or current_day)
                    self._events.record(
                        EventType.PURCHASE_ORDER_DELIVERED,
                        current_day,
                        entity_type="purchase_order",
                        entity_id=po.id,
                        details={"external_order_id": po.external_order_id},
                    )
                    delivered.append(po)
                elif remote_status == PurchaseOrderStatus.CONFIRMED:
                    self._events.record(
                        EventType.PURCHASE_ORDER_CONFIRMED,
                        current_day,
                        entity_type="purchase_order",
                        entity_id=po.id,
                    )
                elif remote_status == PurchaseOrderStatus.IN_PROGRESS:
                    self._events.record(
                        EventType.PURCHASE_ORDER_IN_PROGRESS,
                        current_day,
                        entity_type="purchase_order",
                        entity_id=po.id,
                    )
                elif remote_status == PurchaseOrderStatus.SHIPPED:
                    self._events.record(
                        EventType.PURCHASE_ORDER_SHIPPED,
                        current_day,
                        entity_type="purchase_order",
                        entity_id=po.id,
                    )
                elif remote_status in (
                    PurchaseOrderStatus.CANCELLED,
                    PurchaseOrderStatus.REJECTED,
                ):
                    event_type = (
                        EventType.PURCHASE_ORDER_CANCELLED
                        if remote_status == PurchaseOrderStatus.CANCELLED
                        else EventType.PURCHASE_ORDER_REJECTED
                    )
                    self._events.record(
                        event_type,
                        current_day,
                        entity_type="purchase_order",
                        entity_id=po.id,
                    )

        return delivered
