"""Day-advance orchestration for the retailer.

Implements PRD-week7 §4.4 in order:

1. Poll the manufacturer for pending POs; deliveries land in stock.
2. Auto-fulfil backordered customer orders that have stock now.
3. Increment `current_day` and emit a `DAY_ADVANCED` event.

Step ordering matters: deliveries arrive *before* we look at the
backorder queue, so a delivery on day N can satisfy a customer order
backordered on day N-2 in the same tick.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import EventType
from app.services.customer_order_service import CustomerOrderService
from app.services.event_service import EventService
from app.services.manufacturer_client import ManufacturerClient
from app.services.purchase_order_service import PurchaseOrderService
from app.services.sim_state_service import SimStateService


class DayService:
    def __init__(self, db: Session, manufacturer_client: ManufacturerClient) -> None:
        self.db = db
        self.client = manufacturer_client
        self.sim_state = SimStateService(db)
        self.events = EventService(db)
        self.purchase_orders = PurchaseOrderService(db, manufacturer_client)
        self.customer_orders = CustomerOrderService(db)

    def advance_day(self) -> dict[str, Any]:
        """Run one day's pipeline; commit; return a summary dict."""

        previous_day = self.sim_state.get_current_day()

        po_results = self.purchase_orders.poll_pending_orders(previous_day)
        deliveries = sum(1 for r in po_results if r.get("status") == "DELIVERED")

        fulfilled = self.customer_orders.auto_fulfil_backorders(previous_day)

        new_day = previous_day + 1
        self.sim_state.set_current_day(new_day)
        self.events.record(
            EventType.DAY_ADVANCED,
            new_day,
            entity_type="sim_state",
            details={
                "previous_day": previous_day,
                "current_day": new_day,
                "purchase_orders_delivered": deliveries,
                "backorders_fulfilled": len(fulfilled),
            },
        )

        self.db.commit()

        return {
            "previous_day": previous_day,
            "current_day": new_day,
            "purchase_orders_delivered": deliveries,
            "backorders_fulfilled": len(fulfilled),
            "po_poll_results": po_results,
        }
