"""Advance the retailer's simulated day.

Implements the day-advance sequence from `docs/PRD-week7.md` §4.4:

1. Poll the manufacturer for each in-flight purchase order.
2. For every order that just became DELIVERED: add printers to stock.
3. Auto-fulfill backordered customer orders FIFO per model.
4. Increment `current_day`.
5. Write a DAY_ADVANCED event.

Wholesale-price refresh (step 3 in the PRD) is deferred to M3, when the
manufacturer's `GET /api/prices` endpoint exists.
"""

from __future__ import annotations

from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.models.models import EventType
from app.services.event_service import EventService
from app.services.order_service import OrderService
from app.services.purchase_service import PurchaseService
from app.services.sim_state_service import SimStateService
from app.services.stock_service import StockService


class DayAdvanceResult:
    def __init__(
        self,
        previous_day: int,
        current_day: int,
        deliveries_received: int,
        backorders_fulfilled: int,
    ) -> None:
        self.previous_day = previous_day
        self.current_day = current_day
        self.deliveries_received = deliveries_received
        self.backorders_fulfilled = backorders_fulfilled

    def as_dict(self) -> dict[str, int]:
        return {
            "previous_day": self.previous_day,
            "current_day": self.current_day,
            "deliveries_received": self.deliveries_received,
            "backorders_fulfilled": self.backorders_fulfilled,
        }


class DayService:
    def __init__(
        self,
        db: Session,
        manufacturer_url: str,
        http_transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._db = db
        self._purchase = PurchaseService(db, manufacturer_url, http_transport)
        self._stock = StockService(db)
        self._orders = OrderService(db)
        self._events = EventService(db)
        self._sim_state = SimStateService(db)

    def advance(self) -> DayAdvanceResult:
        """Process one simulated day and return a summary."""
        current_day = self._sim_state.get_current_day()
        new_day = current_day + 1

        # 1. Poll manufacturer; collect newly delivered purchase orders.
        delivered_pos = self._purchase.poll_deliveries(new_day)

        # 2. For each delivered PO, add to stock and auto-fulfill backorders.
        total_backorders_fulfilled = 0
        for po in delivered_pos:
            self._stock.add(po.catalog_item_id, po.quantity)
            self._events.record(
                EventType.STOCK_RECEIVED,
                new_day,
                entity_type="purchase_order",
                entity_id=po.id,
                details={"quantity": po.quantity},
            )
            fulfilled = self._orders.auto_fulfill_backorders(
                po.catalog_item_id, new_day
            )
            total_backorders_fulfilled += len(fulfilled)

        # 3. Increment day and write summary event.
        self._sim_state.set_current_day(new_day)
        self._events.record(
            EventType.DAY_ADVANCED,
            new_day,
            details={
                "previous_day": current_day,
                "deliveries_received": len(delivered_pos),
                "backorders_fulfilled": total_backorders_fulfilled,
            },
        )
        self._db.commit()

        return DayAdvanceResult(
            previous_day=current_day,
            current_day=new_day,
            deliveries_received=len(delivered_pos),
            backorders_fulfilled=total_backorders_fulfilled,
        )
