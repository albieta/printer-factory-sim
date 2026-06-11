"""Advance the provider's simulated day.

Implements the day-advance behaviour from `docs/PRD-week6.md` §5.3.
Stock is reserved at order placement (see `order_service`), so the
"stock check" inside this routine collapses to the trivial observation
that every PENDING order has already had its inventory deducted; it
just needs to ship and, when due, deliver.

Order of operations (matches the PRD):

1. Move SHIPPED orders whose `expected_delivery_day == new_day` to
   DELIVERED. `new_day = current_day + 1`.
2. For PENDING orders, walk the lifecycle to SHIPPED, recording one
   event per intermediate transition (CONFIRMED, IN_PROGRESS, SHIPPED)
   so the audit log shows the full state machine even though the
   provider executes it atomically.
3. Increment `current_day` and write a `DAY_ADVANCED` summary event.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import EventType, Order, OrderStatus
from app.services.event_service import EventService
from app.services.sim_state_service import SimStateService


class DayService:
    """Run a single simulated-day tick on the provider."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.events = EventService(db)
        self.sim_state = SimStateService(db)

    def advance(self) -> dict[str, int]:
        """Process one day and return a small summary dict."""

        current_day = self.sim_state.get_current_day()
        new_day = current_day + 1

        orders_delivered = self._deliver_due_orders(new_day)
        orders_shipped = self._ship_pending_orders(new_day)

        self.sim_state.set_current_day(new_day)

        self.events.record(
            EventType.DAY_ADVANCED,
            new_day,
            details={
                "previous_day": current_day,
                "orders_shipped": orders_shipped,
                "orders_delivered": orders_delivered,
            },
        )
        self.db.commit()

        return {
            "previous_day": current_day,
            "current_day": new_day,
            "orders_shipped": orders_shipped,
            "orders_delivered": orders_delivered,
        }

    def _deliver_due_orders(self, new_day: int) -> int:
        """Transition SHIPPED orders to DELIVERED when they come due.

        An order is due on the day equal to its `expected_delivery_day`.
        """

        due = (
            self.db.query(Order)
            .filter(Order.status == OrderStatus.SHIPPED)
            .filter(Order.expected_delivery_day <= new_day)
            .all()
        )
        for order in due:
            order.status = OrderStatus.DELIVERED
            order.delivered_day = new_day
            self.events.record(
                EventType.ORDER_DELIVERED,
                new_day,
                entity_type="order",
                entity_id=order.id,
                details={
                    "buyer": order.buyer,
                    "product_id": order.product_id,
                    "quantity": order.quantity,
                    "expected_delivery_day": order.expected_delivery_day,
                },
            )
        return len(due)

    def _ship_pending_orders(self, new_day: int) -> int:
        """Walk PENDING orders through CONFIRMED → IN_PROGRESS → SHIPPED.

        Stock has already been reserved at placement, so this method
        does not touch the `Stock` table. One event per intermediate
        transition keeps the audit log faithful to the documented state
        machine.
        """

        pending = (
            self.db.query(Order)
            .filter(Order.status == OrderStatus.PENDING)
            .all()
        )
        for order in pending:
            order.status = OrderStatus.CONFIRMED
            self.events.record(
                EventType.ORDER_CONFIRMED,
                new_day,
                entity_type="order",
                entity_id=order.id,
                details={"buyer": order.buyer, "quantity": order.quantity},
            )

            order.status = OrderStatus.IN_PROGRESS
            self.events.record(
                EventType.ORDER_IN_PROGRESS,
                new_day,
                entity_type="order",
                entity_id=order.id,
                details={"buyer": order.buyer, "quantity": order.quantity},
            )

            order.status = OrderStatus.SHIPPED
            order.shipped_day = new_day
            self.events.record(
                EventType.ORDER_SHIPPED,
                new_day,
                entity_type="order",
                entity_id=order.id,
                details={
                    "buyer": order.buyer,
                    "quantity": order.quantity,
                    "shipped_day": new_day,
                    "expected_delivery_day": order.expected_delivery_day,
                },
            )
        return len(pending)
