"""Wholesale sales service — manufacturer sells finished printers to the retailer."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import (
    BillOfMaterials,
    Event,
    EventType,
    Inventory,
    MfgDayCounter,
    Product,
    ProductType,
    SalesOrder,
    SalesOrderStatus,
    SimulationConfig,
    WholesalePrice,
)

_DEFAULT_WHOLESALE: dict[str, tuple[Decimal, int]] = {
    "Basic300": (Decimal("750.00"), 3),
    "Pro450": (Decimal("1100.00"), 3),
    "Elite700": (Decimal("1650.00"), 4),
}


class SalesError(Exception):
    pass


class ModelNotFoundError(SalesError):
    pass


class NoPriceSetError(SalesError):
    pass


class SalesService:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ── helpers ───────────────────────────────────────────────────────────────

    def _sim_date(self) -> date:
        cfg = self._db.query(SimulationConfig).filter_by(id=1).one_or_none()
        return cfg.sim_date if cfg is not None else date.today()

    def _counter_row(self) -> MfgDayCounter:
        row = self._db.query(MfgDayCounter).filter_by(id=1).one_or_none()
        if row is None:
            row = MfgDayCounter(id=1, current_day=0)
            self._db.add(row)
            self._db.flush()
        return row

    # ── day counter ───────────────────────────────────────────────────────────

    def get_current_day(self) -> int:
        return self._counter_row().current_day

    def increment_day(self) -> int:
        """Increment integer day counter and return the new value."""
        row = self._counter_row()
        row.current_day += 1
        self._db.flush()
        return row.current_day

    # ── wholesale prices ──────────────────────────────────────────────────────

    def list_prices(self) -> list[WholesalePrice]:
        return (
            self._db.query(WholesalePrice)
            .join(WholesalePrice.product)
            .order_by(Product.name)
            .all()
        )

    def get_price_for_model(self, model_name: str) -> Optional[WholesalePrice]:
        return (
            self._db.query(WholesalePrice)
            .join(WholesalePrice.product)
            .filter(Product.name == model_name)
            .one_or_none()
        )

    def set_price(
        self, model_name: str, price: Decimal, lead_time_days: int = 3
    ) -> WholesalePrice:
        product = (
            self._db.query(Product)
            .filter(Product.name == model_name, Product.type == ProductType.PRINTER)
            .one_or_none()
        )
        if product is None:
            raise ModelNotFoundError(f"Printer model {model_name!r} not found")

        wp = (
            self._db.query(WholesalePrice)
            .filter_by(product_id=product.id)
            .one_or_none()
        )
        if wp is None:
            wp = WholesalePrice(
                product_id=product.id,
                price=price,
                lead_time_days=lead_time_days,
            )
            self._db.add(wp)
        else:
            wp.price = price
            wp.lead_time_days = lead_time_days
        self._db.flush()

        self._db.add(
            Event(
                event_type=EventType.WHOLESALE_PRICE_CHANGED,
                sim_date=self._sim_date(),
                details={
                    "model": model_name,
                    "price": float(price),
                    "lead_time_days": lead_time_days,
                },
            )
        )
        return wp

    # ── sales orders ──────────────────────────────────────────────────────────

    def create_order(
        self, model_name: str, quantity: int, buyer_name: str
    ) -> SalesOrder:
        """Accept a purchase order from a retailer and return a SalesOrder."""
        if quantity <= 0:
            raise SalesError("quantity must be positive")

        wp = self.get_price_for_model(model_name)
        if wp is None:
            raise NoPriceSetError(
                f"No wholesale price configured for {model_name!r}"
            )

        current_day = self.get_current_day()
        unit_price = wp.price
        total_price = unit_price * quantity
        expected_delivery_day = current_day + wp.lead_time_days

        order = SalesOrder(
            product_id=wp.product_id,
            quantity=quantity,
            buyer_name=buyer_name,
            unit_price=unit_price,
            total_price=total_price,
            placed_day=current_day,
            expected_delivery_day=expected_delivery_day,
            status=SalesOrderStatus.PENDING,
        )
        self._db.add(order)
        self._db.flush()

        self._db.add(
            Event(
                event_type=EventType.SALES_ORDER_PLACED,
                sim_date=self._sim_date(),
                details={
                    "order_id": order.id,
                    "model": model_name,
                    "quantity": quantity,
                    "buyer": buyer_name,
                    "expected_delivery_day": expected_delivery_day,
                },
            )
        )
        return order

    def get_order(self, order_id: int) -> Optional[SalesOrder]:
        return self._db.query(SalesOrder).filter_by(id=order_id).one_or_none()

    def list_orders(self) -> list[SalesOrder]:
        return (
            self._db.query(SalesOrder).order_by(SalesOrder.id.desc()).all()
        )

    def process_deliveries(self, current_day: int) -> list[SalesOrder]:
        """Mark PENDING and RELEASED sales orders as DELIVERED when their delivery day has arrived."""
        due = (
            self._db.query(SalesOrder)
            .filter(
                SalesOrder.status.in_(
                    [SalesOrderStatus.PENDING, SalesOrderStatus.RELEASED]
                ),
                SalesOrder.expected_delivery_day <= current_day,
            )
            .all()
        )
        sim_date = self._sim_date()
        delivered: list[SalesOrder] = []
        for order in due:
            order.status = SalesOrderStatus.DELIVERED
            order.delivered_day = current_day
            self._db.add(
                Event(
                    event_type=EventType.SALES_ORDER_DELIVERED,
                    sim_date=sim_date,
                    details={"order_id": order.id, "delivered_day": current_day},
                )
            )
            delivered.append(order)
        return delivered

    # ── production management ─────────────────────────────────────────────────

    def release_order(self, order_id: int) -> SalesOrder:
        """Transition a PENDING sales order to RELEASED after a BOM availability check."""
        order = self.get_order(order_id)
        if order is None:
            raise SalesError(f"Sales order {order_id} not found")
        if order.status != SalesOrderStatus.PENDING:
            raise SalesError(
                f"Order {order_id} is {order.status.value} — only PENDING orders can be released"
            )

        bom_entries = (
            self._db.query(BillOfMaterials)
            .filter_by(finished_product_id=order.product_id)
            .all()
        )
        shortfalls: list[str] = []
        for entry in bom_entries:
            needed = entry.quantity * order.quantity
            inv = (
                self._db.query(Inventory)
                .filter_by(product_id=entry.material_id)
                .one_or_none()
            )
            available = inv.quantity if inv is not None else Decimal("0")
            if available < needed:
                mat_name = entry.material.name if entry.material else entry.material_id
                shortfalls.append(
                    f"{mat_name}: need {float(needed):.0f}, have {float(available):.0f}"
                )
        if shortfalls:
            raise SalesError(
                f"Insufficient materials for order {order_id}: " + "; ".join(shortfalls)
            )

        order.status = SalesOrderStatus.RELEASED
        self._db.flush()
        model_name = order.product.name if order.product else str(order.product_id)
        self._db.add(
            Event(
                event_type=EventType.SALES_ORDER_RELEASED,
                sim_date=self._sim_date(),
                details={
                    "order_id": order_id,
                    "model": model_name,
                    "quantity": order.quantity,
                },
            )
        )
        return order

    def list_released(self) -> list[SalesOrder]:
        """Return all RELEASED sales orders (queued for production)."""
        return (
            self._db.query(SalesOrder)
            .filter(SalesOrder.status == SalesOrderStatus.RELEASED)
            .order_by(SalesOrder.placed_day, SalesOrder.id)
            .all()
        )

    def get_capacity_summary(self) -> dict[str, object]:
        """Return daily assembly capacity and utilisation from released sales orders."""
        from app.services.config_service import ConfigService

        daily_hours = ConfigService(self._db).get_daily_assembly_hours()
        released = self.list_released()

        used_hours = 0.0
        for o in released:
            product = self._db.query(Product).filter_by(id=o.product_id).one_or_none()
            if product and product.assembly_hours:
                used_hours += float(product.assembly_hours) * o.quantity

        available_hours = max(0.0, daily_hours - used_hours)
        utilisation_pct = round((used_hours / daily_hours * 100) if daily_hours > 0 else 0.0, 1)

        return {
            "daily_assembly_hours": daily_hours,
            "used_hours": round(used_hours, 2),
            "available_hours": round(available_hours, 2),
            "utilisation_pct": utilisation_pct,
            "released_orders_count": len(released),
        }

    # ── seeding ───────────────────────────────────────────────────────────────

    def seed_default_prices(self) -> None:
        """Idempotently create default wholesale prices for known printer models."""
        for model_name, (price, lead_days) in _DEFAULT_WHOLESALE.items():
            product = (
                self._db.query(Product)
                .filter(
                    Product.name == model_name, Product.type == ProductType.PRINTER
                )
                .one_or_none()
            )
            if product is None:
                continue
            existing = (
                self._db.query(WholesalePrice)
                .filter_by(product_id=product.id)
                .one_or_none()
            )
            if existing is None:
                self._db.add(
                    WholesalePrice(
                        product_id=product.id,
                        price=price,
                        lead_time_days=lead_days,
                    )
                )
        self._db.flush()
