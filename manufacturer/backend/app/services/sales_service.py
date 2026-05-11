"""Wholesale sales service — manufacturer sells finished printers to the retailer."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import (
    Event,
    EventType,
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
        """Mark PENDING sales orders as DELIVERED when their delivery day has arrived."""
        due = (
            self._db.query(SalesOrder)
            .filter(
                SalesOrder.status == SalesOrderStatus.PENDING,
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
