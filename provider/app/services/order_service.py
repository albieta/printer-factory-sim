"""Order intake for the provider app.

Implements the placement half of the order lifecycle from
`docs/PRD-week6.md` §5.1. Day-advance transitions (CONFIRMED → SHIPPED →
DELIVERED) live in `day_service`.

Two rules from the PRD are enforced here at placement time:

- **Stock check**: an order whose quantity exceeds current on-hand stock
  is rejected immediately. Stock for accepted orders is decremented at
  placement, so two concurrent orders cannot oversubscribe the same
  inventory.
- **Ironclad rule**: parts ordered on day N cannot arrive before day
  `N + lead_time_days`. We persist `expected_delivery_day = placed_day +
  lead_time_days` and refuse to place an order against a product whose
  catalogue lead time is below 1 day (a seed-data sanity check; the seed
  loader already validates this).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import EventType, Order, OrderStatus
from app.services.catalog_service import CatalogService
from app.services.event_service import EventService
from app.services.pricing import calculate_unit_price
from app.services.sim_state_service import SimStateService


class OrderError(Exception):
    """Raised for caller-fixable order-placement problems (bad input)."""


class ProductNotFoundError(OrderError):
    """The requested product id does not exist in the catalogue."""


class OrderService:
    """Create, list, and read orders."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.catalog = CatalogService(db)
        self.events = EventService(db)
        self.sim_state = SimStateService(db)

    def create_order(self, buyer: str, product_id: int, quantity: int) -> Order:
        """Place an order on behalf of `buyer`.

        Returns the persisted `Order`. The order's `status` will be
        `PENDING` for an accepted order and `REJECTED` for one the
        provider cannot fulfil (insufficient stock); both terminal and
        in-flight outcomes are stored so the audit log is complete.
        """

        if not buyer or not buyer.strip():
            raise OrderError("buyer must be a non-empty string")
        if quantity <= 0:
            raise OrderError(f"quantity must be positive, got {quantity}")

        product = self.catalog.get_product(product_id)
        if product is None:
            raise ProductNotFoundError(f"product_id={product_id} not found")

        if product.lead_time_days < 1:
            # Defensive: seed validation already enforces this.
            raise OrderError(
                f"product {product.name!r} has lead_time_days < 1; "
                "ironclad rule requires at least 1 day"
            )

        unit_price = calculate_unit_price(product, quantity)
        total_price = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"))

        placed_day = self.sim_state.get_current_day()
        expected_delivery_day = placed_day + product.lead_time_days

        stock = self.catalog.get_stock(product_id)
        stock_qty = stock.quantity if stock is not None else 0

        if stock_qty < quantity:
            order = Order(
                buyer=buyer,
                product_id=product_id,
                quantity=quantity,
                unit_price=unit_price,
                total_price=total_price,
                placed_day=placed_day,
                expected_delivery_day=expected_delivery_day,
                status=OrderStatus.REJECTED,
                status_reason=(
                    f"insufficient stock: requested {quantity}, available {stock_qty}"
                ),
            )
            self.db.add(order)
            self.db.flush()  # populate order.id for the event rows

            self.events.record(
                EventType.ORDER_PLACED,
                placed_day,
                entity_type="order",
                entity_id=order.id,
                details={
                    "buyer": buyer,
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": str(unit_price),
                    "total_price": str(total_price),
                    "expected_delivery_day": expected_delivery_day,
                },
            )
            self.events.record(
                EventType.ORDER_REJECTED,
                placed_day,
                entity_type="order",
                entity_id=order.id,
                details={"reason": order.status_reason},
            )
            self.db.commit()
            self.db.refresh(order)
            return order

        # Accepted: reserve stock atomically with the order row.
        # stock is guaranteed non-None here: if it were None, stock_qty == 0,
        # and quantity > 0 (validated above), so the rejection branch above
        # would have returned already.
        assert stock is not None
        stock.quantity = stock_qty - quantity

        order = Order(
            buyer=buyer,
            product_id=product_id,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            placed_day=placed_day,
            expected_delivery_day=expected_delivery_day,
            status=OrderStatus.PENDING,
        )
        self.db.add(order)
        self.db.flush()

        self.events.record(
            EventType.ORDER_PLACED,
            placed_day,
            entity_type="order",
            entity_id=order.id,
            details={
                "buyer": buyer,
                "product_id": product_id,
                "quantity": quantity,
                "unit_price": str(unit_price),
                "total_price": str(total_price),
                "expected_delivery_day": expected_delivery_day,
            },
        )
        self.events.record(
            EventType.STOCK_CONSUMED,
            placed_day,
            entity_type="stock",
            entity_id=product_id,
            details={
                "quantity": quantity,
                "remaining": stock.quantity,
                "reason": "order_reserved",
                "order_id": order.id,
            },
        )

        self.db.commit()
        self.db.refresh(order)
        return order

    def list_orders(self, *, status: Optional[OrderStatus] = None) -> list[Order]:
        """Return orders ordered newest-first, with optional status filter."""

        query = self.db.query(Order)
        if status is not None:
            query = query.filter(Order.status == status)
        return query.order_by(Order.id.desc()).all()

    def get_order(self, order_id: int) -> Optional[Order]:
        """Return one order by id, or `None`."""

        return self.db.query(Order).filter_by(id=order_id).one_or_none()
