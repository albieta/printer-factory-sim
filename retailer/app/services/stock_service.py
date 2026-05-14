"""Finished-printer inventory management for the retailer.

`Stock` rows are keyed by `product_name` (the retailer does not share
the manufacturer's product IDs). The service auto-creates a stock row
on the first write, so adding inventory for a freshly-introduced model
never blows up with a `NoResultFound`.

Every state-changing call records an event; the caller commits.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import EventType, Stock
from app.services.event_service import EventService


class StockService:
    """CRUD over the retailer's `stock` table."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.events = EventService(db)

    def list_stock(self) -> list[Stock]:
        return self.db.query(Stock).order_by(Stock.product_name).all()

    def get_stock(self, product_name: str) -> Optional[Stock]:
        return self.db.query(Stock).filter_by(product_name=product_name).one_or_none()

    def get_quantity(self, product_name: str) -> int:
        row = self.get_stock(product_name)
        return 0 if row is None else row.quantity

    def add_stock(self, product_name: str, quantity: int, sim_day: int) -> Stock:
        """Increase on-hand stock and record a `STOCK_ADDED` event."""

        if quantity <= 0:
            raise ValueError("add_stock quantity must be positive")

        row = self.get_stock(product_name)
        if row is None:
            row = Stock(product_name=product_name, quantity=quantity)
            self.db.add(row)
        else:
            row.quantity += quantity

        self.events.record(
            EventType.STOCK_ADDED,
            sim_day,
            entity_type="stock",
            details={"product_name": product_name, "delta": quantity, "new_quantity": row.quantity},
        )
        self.db.flush()
        return row

    def consume_stock(self, product_name: str, quantity: int, sim_day: int) -> Stock:
        """Decrement on-hand stock, asserting it does not go negative."""

        if quantity <= 0:
            raise ValueError("consume_stock quantity must be positive")

        row = self.get_stock(product_name)
        if row is None or row.quantity < quantity:
            available = 0 if row is None else row.quantity
            raise ValueError(
                f"Insufficient stock for {product_name!r}: "
                f"requested {quantity}, available {available}"
            )

        row.quantity -= quantity
        self.events.record(
            EventType.STOCK_CONSUMED,
            sim_day,
            entity_type="stock",
            details={"product_name": product_name, "delta": -quantity, "new_quantity": row.quantity},
        )
        self.db.flush()
        return row
