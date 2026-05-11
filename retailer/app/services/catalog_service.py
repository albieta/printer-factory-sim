"""Catalog and price management for the retailer app."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.models import CatalogItem, EventType
from app.services.event_service import EventService
from app.services.sim_state_service import SimStateService


class CatalogError(Exception):
    pass


class ModelNotFoundError(CatalogError):
    pass


class CatalogService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._events = EventService(db)
        self._sim_state = SimStateService(db)

    def list_items(self) -> list[CatalogItem]:
        return self._db.query(CatalogItem).order_by(CatalogItem.model_name).all()

    def get_by_name(self, model_name: str) -> CatalogItem:
        """Return the CatalogItem for `model_name`, raising if absent."""
        item = (
            self._db.query(CatalogItem)
            .filter_by(model_name=model_name)
            .one_or_none()
        )
        if item is None:
            raise ModelNotFoundError(f"model {model_name!r} not in catalog")
        return item

    def set_price(self, model_name: str, price: Decimal) -> CatalogItem:
        """Update the retail price for a model and emit a PRICE_CHANGED event."""
        if price <= Decimal("0"):
            raise CatalogError("price must be positive")
        item = self.get_by_name(model_name)
        old_price = item.retail_price
        item.retail_price = price
        self._events.record(
            EventType.PRICE_CHANGED,
            self._sim_state.get_current_day(),
            entity_type="catalog_item",
            entity_id=item.id,
            details={"old_price": float(old_price), "new_price": float(price)},
        )
        return item
