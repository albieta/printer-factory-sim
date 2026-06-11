"""Catalog management for the retailer.

The catalog table holds one row per printer model the retailer sells,
together with its current retail price. Setting a retail price requires
a wholesale-price lookup (the floor is `wholesale * (1 + markup/100)`),
so `set_retail_price` takes a `wholesale_price` argument — the caller
fetches it from the manufacturer via `ManufacturerClient` and passes it
in. Keeping the I/O out of this module makes it unit-testable.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import CatalogEntry, EventType
from app.services.event_service import EventService
from app.services.pricing import validate_retail_price


class CatalogService:
    """Read/update the retailer's catalog."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.events = EventService(db)

    def list_catalog(self) -> list[CatalogEntry]:
        return self.db.query(CatalogEntry).order_by(CatalogEntry.product_name).all()

    def get_entry(self, product_name: str) -> Optional[CatalogEntry]:
        return (
            self.db.query(CatalogEntry).filter_by(product_name=product_name).one_or_none()
        )

    def get_retail_price(self, product_name: str) -> Decimal:
        entry = self.get_entry(product_name)
        if entry is None:
            raise ValueError(f"Catalog has no entry for {product_name!r}")
        return entry.retail_price

    def set_retail_price(
        self,
        product_name: str,
        retail_price: Decimal,
        *,
        wholesale_price: Decimal,
        markup_pct: int,
        sim_day: int,
    ) -> CatalogEntry:
        """Update the retail price after enforcing the markup floor.

        Raises `ValueError` if `product_name` is unknown or the new
        price falls below the floor. The caller commits.
        """

        entry = self.get_entry(product_name)
        if entry is None:
            raise ValueError(f"Catalog has no entry for {product_name!r}")

        validate_retail_price(retail_price, wholesale_price, markup_pct)

        previous_price = entry.retail_price
        entry.retail_price = retail_price

        self.events.record(
            EventType.PRICE_CHANGED,
            sim_day,
            entity_type="catalog",
            details={
                "product_name": product_name,
                "previous_price": str(previous_price),
                "new_price": str(retail_price),
                "wholesale_reference": str(wholesale_price),
                "markup_pct": markup_pct,
            },
        )
        self.db.flush()
        return entry
