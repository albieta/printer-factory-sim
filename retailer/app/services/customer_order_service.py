"""Customer-order management for the retailer.

Implements PRD-week7 §4.4:

- `place_order`: if stock is available, fulfil immediately; otherwise
  the order is written as `BACKORDERED`.
- `auto_fulfil_backorders`: called from `DayService.advance_day`,
  promotes backordered orders to fulfilled when stock has arrived.

Pricing snapshot: the order records the retail price *at order time*,
so a later price change does not retroactively adjust historical
orders. The retailer's catalog is the source of truth for that
snapshot.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import (
    CustomerOrder,
    CustomerOrderStatus,
    EventType,
)
from app.services.catalog_service import CatalogService
from app.services.event_service import EventService
from app.services.stock_service import StockService


class CustomerOrderService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.catalog = CatalogService(db)
        self.stock = StockService(db)
        self.events = EventService(db)

    def list_orders(
        self, status: Optional[CustomerOrderStatus] = None
    ) -> list[CustomerOrder]:
        query = self.db.query(CustomerOrder)
        if status is not None:
            query = query.filter(CustomerOrder.status == status)
        return query.order_by(CustomerOrder.id.desc()).all()

    def get_order(self, order_id: int) -> Optional[CustomerOrder]:
        return self.db.query(CustomerOrder).filter_by(id=order_id).one_or_none()

    def place_order(
        self,
        customer: str,
        product_name: str,
        quantity: int,
        sim_day: int,
    ) -> CustomerOrder:
        """Place a customer order; fulfil from stock or mark backordered."""

        if quantity <= 0:
            raise ValueError("quantity must be positive")

        entry = self.catalog.get_entry(product_name)
        if entry is None:
            raise ValueError(f"Catalog has no entry for {product_name!r}")

        unit_price = entry.retail_price
        total_price = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"))

        order = CustomerOrder(
            customer=customer,
            product_name=product_name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            placed_day=sim_day,
            status=CustomerOrderStatus.PENDING,
        )
        self.db.add(order)
        self.db.flush()

        self.events.record(
            EventType.CUSTOMER_ORDER_PLACED,
            sim_day,
            entity_type="customer_order",
            entity_id=order.id,
            details={
                "customer": customer,
                "product_name": product_name,
                "quantity": quantity,
                "unit_price": str(unit_price),
                "total_price": str(total_price),
            },
        )

        available = self.stock.get_quantity(product_name)
        if available >= quantity:
            self.stock.consume_stock(product_name, quantity, sim_day)
            order.status = CustomerOrderStatus.FULFILLED
            order.fulfilled_day = sim_day
            self.events.record(
                EventType.CUSTOMER_ORDER_FULFILLED,
                sim_day,
                entity_type="customer_order",
                entity_id=order.id,
                details={"product_name": product_name, "quantity": quantity},
            )
        else:
            order.status = CustomerOrderStatus.BACKORDERED
            order.status_reason = (
                f"Insufficient stock: requested {quantity}, available {available}"
            )
            self.events.record(
                EventType.CUSTOMER_ORDER_BACKORDERED,
                sim_day,
                entity_type="customer_order",
                entity_id=order.id,
                details={
                    "product_name": product_name,
                    "requested": quantity,
                    "available": available,
                },
            )

        self.db.flush()
        return order

    def cancel_order(self, order_id: int, sim_day: int) -> CustomerOrder:
        """Cancel a pending or backordered order (terminal short-circuit)."""

        order = self.get_order(order_id)
        if order is None:
            raise ValueError(f"Customer order {order_id} not found")
        if order.status not in (CustomerOrderStatus.PENDING, CustomerOrderStatus.BACKORDERED):
            raise ValueError(
                f"Customer order {order_id} cannot be cancelled from state {order.status.value}"
            )

        order.status = CustomerOrderStatus.CANCELLED
        self.events.record(
            EventType.CUSTOMER_ORDER_CANCELLED,
            sim_day,
            entity_type="customer_order",
            entity_id=order.id,
            details={"product_name": order.product_name, "quantity": order.quantity},
        )
        self.db.flush()
        return order

    def mark_backordered(self, order_id: int, sim_day: int) -> CustomerOrder:
        """Explicitly move a pending customer order into the backorder queue."""

        order = self.get_order(order_id)
        if order is None:
            raise ValueError(f"Customer order {order_id} not found")
        if order.status == CustomerOrderStatus.BACKORDERED:
            return order
        if order.status != CustomerOrderStatus.PENDING:
            raise ValueError(
                f"Customer order {order_id} cannot be backordered from state {order.status.value}"
            )

        available = self.stock.get_quantity(order.product_name)
        order.status = CustomerOrderStatus.BACKORDERED
        order.status_reason = (
            f"Manually backordered on day {sim_day}; available stock was {available}"
        )
        self.events.record(
            EventType.CUSTOMER_ORDER_BACKORDERED,
            sim_day,
            entity_type="customer_order",
            entity_id=order.id,
            details={
                "product_name": order.product_name,
                "requested": order.quantity,
                "available": available,
                "manual": True,
            },
        )
        self.db.flush()
        return order

    def auto_fulfil_backorders(self, sim_day: int) -> list[CustomerOrder]:
        """Fulfil any backordered orders whose model now has enough stock.

        Orders are processed oldest-first. Stock is decremented in order;
        an early large order cannot starve later small orders if there
        is enough stock to satisfy the larger one first — this matches
        FIFO queueing intuition.
        """

        backorders = (
            self.db.query(CustomerOrder)
            .filter(CustomerOrder.status == CustomerOrderStatus.BACKORDERED)
            .order_by(CustomerOrder.id.asc())
            .all()
        )

        fulfilled: list[CustomerOrder] = []
        for order in backorders:
            available = self.stock.get_quantity(order.product_name)
            if available < order.quantity:
                continue

            self.stock.consume_stock(order.product_name, order.quantity, sim_day)
            order.status = CustomerOrderStatus.FULFILLED
            order.fulfilled_day = sim_day
            order.status_reason = None
            self.events.record(
                EventType.BACKORDER_FULFILLED,
                sim_day,
                entity_type="customer_order",
                entity_id=order.id,
                details={
                    "product_name": order.product_name,
                    "quantity": order.quantity,
                    "placed_day": order.placed_day,
                    "fulfilled_day": sim_day,
                },
            )
            fulfilled.append(order)

        if fulfilled:
            self.db.flush()
        return fulfilled
