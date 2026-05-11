"""Customer order lifecycle for the retailer app.

Implements the placement and manual-action half of the customer order
state machine from `docs/PRD-week7.md` §4.1:

  pending → fulfilled       (stock available at placement)
  pending → backordered     (no stock at placement)
  backordered → fulfilled   (auto_fulfill_backorders called on day advance)
  pending / backordered → cancelled

Auto-fulfillment of backorders on stock arrival is driven by
`day_service.advance()`, which calls `auto_fulfill_backorders()` after
adding received inventory.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import (
    CatalogItem,
    CustomerOrder,
    CustomerOrderStatus,
    EventType,
)
from app.services.catalog_service import CatalogService, ModelNotFoundError
from app.services.event_service import EventService
from app.services.sim_state_service import SimStateService
from app.services.stock_service import StockService


class OrderError(Exception):
    pass


class OrderService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._catalog = CatalogService(db)
        self._stock = StockService(db)
        self._events = EventService(db)
        self._sim_state = SimStateService(db)

    def place_order(self, model_name: str, quantity: int) -> CustomerOrder:
        """Place a customer order, fulfilling immediately or backordering.

        The retail price at the moment of placement is locked into the
        order row so later price changes do not alter order economics.
        """
        if quantity <= 0:
            raise OrderError("quantity must be positive")

        item = self._catalog.get_by_name(model_name)
        current_day = self._sim_state.get_current_day()
        unit_price: Decimal = item.retail_price
        total_price = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"))

        order = CustomerOrder(
            catalog_item_id=item.id,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            placed_day=current_day,
            status=CustomerOrderStatus.PENDING,
        )
        self._db.add(order)
        self._db.flush()

        self._events.record(
            EventType.CUSTOMER_ORDER_PLACED,
            current_day,
            entity_type="customer_order",
            entity_id=order.id,
            details={"model": model_name, "quantity": quantity},
        )

        available = self._stock.get_quantity(item.id)
        if available >= quantity:
            self._stock.consume(item.id, quantity)
            order.status = CustomerOrderStatus.FULFILLED
            order.fulfilled_day = current_day
            self._events.record(
                EventType.CUSTOMER_ORDER_FULFILLED,
                current_day,
                entity_type="customer_order",
                entity_id=order.id,
                details={"model": model_name, "quantity": quantity, "from_stock": True},
            )
        else:
            order.status = CustomerOrderStatus.BACKORDERED
            self._events.record(
                EventType.CUSTOMER_ORDER_BACKORDERED,
                current_day,
                entity_type="customer_order",
                entity_id=order.id,
                details={
                    "model": model_name,
                    "quantity": quantity,
                    "available": available,
                },
            )

        self._db.commit()
        self._db.refresh(order)
        return order

    def fulfill(self, order_id: int) -> CustomerOrder:
        """Manually ship one pending or backordered order from stock."""
        order = self._get_or_raise(order_id)
        if order.status not in (
            CustomerOrderStatus.PENDING,
            CustomerOrderStatus.BACKORDERED,
        ):
            raise OrderError(
                f"order {order_id} is {order.status.value}; cannot fulfill"
            )
        current_day = self._sim_state.get_current_day()
        self._stock.consume(order.catalog_item_id, order.quantity)
        order.status = CustomerOrderStatus.FULFILLED
        order.fulfilled_day = current_day
        self._events.record(
            EventType.CUSTOMER_ORDER_FULFILLED,
            current_day,
            entity_type="customer_order",
            entity_id=order.id,
            details={"manual": True},
        )
        self._db.commit()
        self._db.refresh(order)
        return order

    def mark_backordered(self, order_id: int) -> CustomerOrder:
        """Manually move a pending order to backordered."""
        order = self._get_or_raise(order_id)
        if order.status != CustomerOrderStatus.PENDING:
            raise OrderError(
                f"order {order_id} is {order.status.value}; can only backorder PENDING orders"
            )
        current_day = self._sim_state.get_current_day()
        order.status = CustomerOrderStatus.BACKORDERED
        self._events.record(
            EventType.CUSTOMER_ORDER_BACKORDERED,
            current_day,
            entity_type="customer_order",
            entity_id=order.id,
            details={"manual": True},
        )
        self._db.commit()
        self._db.refresh(order)
        return order

    def cancel(self, order_id: int) -> CustomerOrder:
        """Cancel a pending or backordered order."""
        order = self._get_or_raise(order_id)
        if order.status not in (
            CustomerOrderStatus.PENDING,
            CustomerOrderStatus.BACKORDERED,
        ):
            raise OrderError(
                f"order {order_id} is {order.status.value}; cannot cancel"
            )
        current_day = self._sim_state.get_current_day()
        order.status = CustomerOrderStatus.CANCELLED
        self._events.record(
            EventType.CUSTOMER_ORDER_CANCELLED,
            current_day,
            entity_type="customer_order",
            entity_id=order.id,
        )
        self._db.commit()
        self._db.refresh(order)
        return order

    def list_orders(
        self, *, status: Optional[CustomerOrderStatus] = None
    ) -> list[CustomerOrder]:
        query = self._db.query(CustomerOrder)
        if status is not None:
            query = query.filter(CustomerOrder.status == status)
        return query.order_by(CustomerOrder.id.desc()).all()

    def get_order(self, order_id: int) -> Optional[CustomerOrder]:
        return self._db.query(CustomerOrder).filter_by(id=order_id).one_or_none()

    def auto_fulfill_backorders(
        self, catalog_item_id: int, current_day: int
    ) -> list[CustomerOrder]:
        """Fulfill backordered orders FIFO until stock is exhausted.

        Called by `day_service.advance()` after stock is received from
        the manufacturer. Orders are processed oldest-first (FIFO by id).
        """
        backorders = (
            self._db.query(CustomerOrder)
            .filter(CustomerOrder.catalog_item_id == catalog_item_id)
            .filter(CustomerOrder.status == CustomerOrderStatus.BACKORDERED)
            .order_by(CustomerOrder.id.asc())
            .all()
        )
        fulfilled: list[CustomerOrder] = []
        for order in backorders:
            available = self._stock.get_quantity(catalog_item_id)
            if available < order.quantity:
                break
            self._stock.consume(catalog_item_id, order.quantity)
            order.status = CustomerOrderStatus.FULFILLED
            order.fulfilled_day = current_day
            self._events.record(
                EventType.CUSTOMER_ORDER_FULFILLED,
                current_day,
                entity_type="customer_order",
                entity_id=order.id,
                details={"auto_fulfilled": True},
            )
            fulfilled.append(order)
        return fulfilled

    def _get_or_raise(self, order_id: int) -> CustomerOrder:
        order = self._db.query(CustomerOrder).filter_by(id=order_id).one_or_none()
        if order is None:
            raise OrderError(f"customer order {order_id} not found")
        return order
