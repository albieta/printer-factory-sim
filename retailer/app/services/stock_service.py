"""Finished-printer inventory for the retailer app."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import CatalogItem, Stock


class StockError(Exception):
    pass


class InsufficientStockError(StockError):
    pass


class StockService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_quantity(self, catalog_item_id: int) -> int:
        """Return current on-hand quantity for a catalog item."""
        row = (
            self._db.query(Stock)
            .filter_by(catalog_item_id=catalog_item_id)
            .one_or_none()
        )
        return row.quantity if row is not None else 0

    def list_stock(self) -> list[Any]:
        """Return all (CatalogItem, Stock) pairs ordered by model name."""
        return (
            self._db.query(CatalogItem, Stock)
            .outerjoin(Stock, Stock.catalog_item_id == CatalogItem.id)
            .order_by(CatalogItem.model_name)
            .all()
        )

    def add(self, catalog_item_id: int, quantity: int) -> Stock:
        """Increase stock by `quantity` units. Creates row if absent."""
        if quantity <= 0:
            raise StockError("quantity must be positive")
        row = (
            self._db.query(Stock)
            .filter_by(catalog_item_id=catalog_item_id)
            .one_or_none()
        )
        if row is None:
            row = Stock(catalog_item_id=catalog_item_id, quantity=quantity)
            self._db.add(row)
        else:
            row.quantity += quantity
        return row

    def consume(self, catalog_item_id: int, quantity: int) -> Stock:
        """Decrease stock by `quantity` units, raising if insufficient."""
        if quantity <= 0:
            raise StockError("quantity must be positive")
        row = (
            self._db.query(Stock)
            .filter_by(catalog_item_id=catalog_item_id)
            .one_or_none()
        )
        available = row.quantity if row is not None else 0
        if available < quantity:
            raise InsufficientStockError(
                f"need {quantity}, have {available}"
            )
        assert row is not None
        row.quantity -= quantity
        return row
