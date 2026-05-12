"""Catalog and price management for the retailer app."""

from __future__ import annotations

from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.models.models import CatalogItem, EventType
from app.services.event_service import EventService
from app.services.sim_state_service import SimStateService

MIN_MARKUP_FACTOR = Decimal("1.15")


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

    def _fetch_wholesale_price(self, manufacturer_url: str, model_name: str) -> Decimal:
        """Fetch the current wholesale price for `model_name` from the manufacturer API."""
        url = manufacturer_url.rstrip("/") + "/api/sales/prices"
        try:
            resp = httpx.get(url, timeout=5.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise CatalogError(
                f"cannot verify wholesale price: manufacturer unreachable ({exc})"
            ) from exc
        prices: list[dict[str, object]] = resp.json()
        for entry in prices:
            if entry.get("model_name") == model_name:
                return Decimal(str(entry["price"]))
        raise CatalogError(
            f"manufacturer has no wholesale price set for {model_name!r}"
        )

    def set_price(
        self, model_name: str, price: Decimal, manufacturer_url: str
    ) -> CatalogItem:
        """Update the retail price, enforcing a minimum 15 % markup over wholesale.

        Raises CatalogError if the manufacturer is unreachable or the proposed
        price falls below wholesale_price × 1.15.
        """
        if price <= Decimal("0"):
            raise CatalogError("price must be positive")
        wholesale = self._fetch_wholesale_price(manufacturer_url, model_name)
        floor = (wholesale * MIN_MARKUP_FACTOR).quantize(Decimal("0.01"))
        if price < floor:
            raise CatalogError(
                f"price {float(price):.2f} is below the minimum markup floor "
                f"(wholesale {float(wholesale):.2f} + 15% = {float(floor):.2f})"
            )
        item = self.get_by_name(model_name)
        old_price = item.retail_price
        item.retail_price = price
        self._events.record(
            EventType.PRICE_CHANGED,
            self._sim_state.get_current_day(),
            entity_type="catalog_item",
            entity_id=item.id,
            details={
                "old_price": float(old_price),
                "new_price": float(price),
                "wholesale_price": float(wholesale),
                "floor": float(floor),
            },
        )
        return item
