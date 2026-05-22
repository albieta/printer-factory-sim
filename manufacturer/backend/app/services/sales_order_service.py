"""Inbound sales orders from retailers.

The manufacturer accepts orders for finished printers from retailer apps.
Each order follows the lifecycle:

  PENDING → CONFIRMED → IN_PROGRESS → SHIPPED → DELIVERED
          └─ REJECTED                                       (capacity / product)
          └─ CANCELLED                                      (operator action)

PENDING:     order received, not yet reviewed.
CONFIRMED:   operator (or agent) released it to production; a ManufacturingOrder
             has been created for it.
IN_PROGRESS: the day-advance service has started consuming materials.
SHIPPED:     production complete; goods dispatched.
DELIVERED:   retailer has been notified and polled the status.

The day-advance progression (CONFIRMED → DELIVERED) is handled by
`SimulationService.advance_day()` in Milestone 6. This service only
handles create, list, get, and the manual release step.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.models import (
    Event,
    EventType,
    ManufacturingOrder,
    OrderStatus,
    Product,
    ProductType,
    SalesOrder,
    SalesOrderStatus,
    WholesalePrice,
)
from app.services.config_service import ConfigService
from app.services.financial_service import FinancialService

# How many day-advance ticks a SalesOrder spends in each in-flight state.
_PRODUCTION_DAYS = 1   # IN_PROGRESS → SHIPPED after this many ticks
_SHIPPING_DAYS = 1     # SHIPPED → DELIVERED after this many ticks

# Default lead time (days) from release to expected shipment.
DEFAULT_LEAD_DAYS = 3

SCHEMA_VERSION = 1


def _next_so_reference(db: Session, placed_day: int) -> str:
    seq = db.query(SalesOrder).filter(SalesOrder.placed_day == placed_day).count() + 1
    return f"SO-{placed_day:04d}-{seq:03d}"


class SalesOrderService:
    """Create and manage inbound retailer sales orders."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = ConfigService(db)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _find_printer(self, product_name: str) -> Optional[Product]:
        return (
            self.db.query(Product)
            .filter(Product.name == product_name, Product.type == ProductType.PRINTER)
            .one_or_none()
        )

    def _wholesale_price(self, product_id: str) -> Decimal:
        row = (
            self.db.query(WholesalePrice)
            .filter(WholesalePrice.product_id == product_id)
            .one_or_none()
        )
        return row.price if row is not None else Decimal("0.00")

    # ── public API ────────────────────────────────────────────────────────────

    def list_orders(self, status: Optional[SalesOrderStatus] = None) -> list[SalesOrder]:
        q = self.db.query(SalesOrder)
        if status is not None:
            q = q.filter(SalesOrder.status == status)
        return q.order_by(SalesOrder.placed_day.desc(), SalesOrder.id).all()

    def get_order(self, order_id: str) -> Optional[SalesOrder]:
        order = self.db.query(SalesOrder).filter_by(id=order_id).one_or_none()
        if order is None:
            order = self.db.query(SalesOrder).filter_by(reference_code=order_id).one_or_none()
        return order

    def create_from_retailer(
        self,
        retailer_name: str,
        product_name: str,
        quantity: int,
    ) -> SalesOrder:
        """Accept an order from a retailer; return a PENDING SalesOrder.

        Raises `ValueError` for unknown models or non-positive quantity.
        The caller commits.
        """

        if quantity <= 0:
            raise ValueError("quantity must be positive")

        product = self._find_printer(product_name)
        if product is None:
            raise ValueError(f"No printer model {product_name!r} in the catalog")

        sim_day = self.config.get_sim_day()
        unit_price = self._wholesale_price(product.id)
        total_price = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"))
        reference_code = _next_so_reference(self.db, sim_day)

        order = SalesOrder(
            reference_code=reference_code,
            retailer_name=retailer_name,
            product_id=product.id,
            quantity=quantity,
            status=SalesOrderStatus.PENDING,
            unit_price=unit_price,
            total_price=total_price,
            placed_day=sim_day,
            expected_ship_day=sim_day + DEFAULT_LEAD_DAYS,
        )
        self.db.add(order)
        self.db.flush()

        self.db.add(
            Event(
                event_type=EventType.SALES_ORDER_PLACED,
                sim_date=self.config.get_sim_date(),
                details={
                    "order_id": order.id,
                    "reference_code": reference_code,
                    "retailer_name": retailer_name,
                    "product_name": product_name,
                    "quantity": quantity,
                    "unit_price": str(unit_price),
                    "total_price": str(total_price),
                },
            )
        )
        self.db.flush()
        return order

    def release_to_production(self, order_id: str) -> dict[str, Any]:
        """Move a PENDING SalesOrder to CONFIRMED and queue a ManufacturingOrder.

        Returns a result dict with `success`, `order`, and optionally `error`.
        The caller commits.
        """

        order = self.get_order(order_id)
        if order is None:
            return {"success": False, "error": f"SalesOrder {order_id!r} not found"}
        if order.status != SalesOrderStatus.PENDING:
            return {
                "success": False,
                "error": f"SalesOrder is {order.status.value}, expected PENDING",
            }

        sim_date = self.config.get_sim_date()

        mfg_order = ManufacturingOrder(
            product_id=order.product_id,
            quantity=order.quantity,
            status=OrderStatus.RELEASED,
            created_date=sim_date,
            released_date=sim_date,
        )
        self.db.add(mfg_order)
        self.db.flush()

        # Back-fill the reference code on the ManufacturingOrder.
        from app.services.reference_service import next_reference_code

        mfg_order.reference_code = next_reference_code(
            self.db, ManufacturingOrder, "MO", "created_date", sim_date
        )

        order.status = SalesOrderStatus.CONFIRMED
        order.linked_mfg_order_id = mfg_order.id
        self.db.add(
            Event(
                event_type=EventType.SALES_ORDER_RELEASED,
                sim_date=sim_date,
                details={
                    "order_id": order.id,
                    "reference_code": order.reference_code,
                    "mfg_order_id": mfg_order.id,
                    "mfg_reference_code": mfg_order.reference_code,
                    "product_id": order.product_id,
                    "quantity": order.quantity,
                },
            )
        )
        self.db.flush()
        return {"success": True, "order": order, "mfg_order_id": mfg_order.id}

    def get_production_status(self) -> list[dict[str, Any]]:
        """Return all non-terminal sales orders with their current status."""

        active = (
            self.db.query(SalesOrder)
            .filter(
                SalesOrder.status.in_(
                    [
                        SalesOrderStatus.PENDING,
                        SalesOrderStatus.CONFIRMED,
                        SalesOrderStatus.IN_PROGRESS,
                        SalesOrderStatus.SHIPPED,
                    ]
                )
            )
            .order_by(SalesOrder.placed_day.asc())
            .all()
        )
        return [self.serialize_order(o) for o in active]

    def progress_sales_orders(self, sim_day: int) -> dict[str, int]:
        """Advance SalesOrder states as part of day-advance.

        Called *after* `execute_production()` so any ManufacturingOrders
        that completed this tick are already in COMPLETED state.

        Three transitions in fixed order:
        1. CONFIRMED → IN_PROGRESS  (linked MO just completed)
        2. IN_PROGRESS → SHIPPED    (one tick in production elapsed)
        3. SHIPPED → DELIVERED      (one tick in transit elapsed)

        Returns counts for the day-advance summary.
        """

        sim_date = self.config.get_sim_date()
        counts = {"in_progress": 0, "shipped": 0, "delivered": 0}

        # ── 1. CONFIRMED → IN_PROGRESS ────────────────────────────────────────
        confirmed = (
            self.db.query(SalesOrder)
            .filter(
                SalesOrder.status == SalesOrderStatus.CONFIRMED,
                SalesOrder.linked_mfg_order_id.is_not(None),
            )
            .all()
        )
        for so in confirmed:
            mfg = (
                self.db.query(ManufacturingOrder)
                .filter_by(id=so.linked_mfg_order_id)
                .one_or_none()
            )
            if mfg is None or mfg.status != OrderStatus.COMPLETED:
                continue
            so.status = SalesOrderStatus.IN_PROGRESS
            so.in_progress_day = sim_day
            self.db.add(
                Event(
                    event_type=EventType.SALES_ORDER_RELEASED,  # re-use; no separate type yet
                    sim_date=sim_date,
                    details={
                        "transition": "CONFIRMED_TO_IN_PROGRESS",
                        "order_id": so.id,
                        "sim_day": sim_day,
                    },
                )
            )
            counts["in_progress"] += 1

        self.db.flush()

        # ── 2. IN_PROGRESS → SHIPPED ─────────────────────────────────────────
        in_progress = (
            self.db.query(SalesOrder)
            .filter(
                SalesOrder.status == SalesOrderStatus.IN_PROGRESS,
                SalesOrder.in_progress_day < sim_day,
            )
            .all()
        )
        for so in in_progress:
            so.status = SalesOrderStatus.SHIPPED
            so.shipped_day = sim_day
            so.expected_ship_day = sim_day  # update to actual
            self.db.add(
                Event(
                    event_type=EventType.SALES_ORDER_SHIPPED,
                    sim_date=sim_date,
                    details={
                        "order_id": so.id,
                        "reference_code": so.reference_code,
                        "shipped_day": sim_day,
                    },
                )
            )
            counts["shipped"] += 1

        self.db.flush()

        # ── 3. SHIPPED → DELIVERED ────────────────────────────────────────────
        shipped = (
            self.db.query(SalesOrder)
            .filter(
                SalesOrder.status == SalesOrderStatus.SHIPPED,
                SalesOrder.shipped_day < sim_day,
            )
            .all()
        )
        financial_service = FinancialService(self.db)
        for so in shipped:
            so.status = SalesOrderStatus.DELIVERED
            so.delivered_day = sim_day
            self.db.add(
                Event(
                    event_type=EventType.SALES_ORDER_DELIVERED,
                    sim_date=sim_date,
                    details={
                        "order_id": so.id,
                        "reference_code": so.reference_code,
                        "delivered_day": sim_day,
                    },
                )
            )
            product_name = so.product.name if so.product else f"Product {so.product_id}"
            financial_service.record_product_sold(
                sim_day,
                float(so.total_price),
                product_name,
                so.quantity
            )
            counts["delivered"] += 1

        self.db.flush()
        return counts

    def serialize_order(self, order: SalesOrder) -> dict[str, Any]:
        """Return the wire format the retailer expects."""

        return {
            "id": order.id,
            "reference_code": order.reference_code,
            "retailer": order.retailer_name,
            "model": order.product.name if order.product else None,
            "quantity": order.quantity,
            "unit_price": str(order.unit_price),
            "total_price": str(order.total_price),
            "placed_day": order.placed_day,
            "expected_ship_day": order.expected_ship_day,
            "shipped_day": order.shipped_day,
            "delivered_day": order.delivered_day,
            "status": order.status.value,
            "status_reason": order.status_reason,
        }
