"""Wholesale price management for finished printer models.

The manufacturer publishes one wholesale price per printer model. The retailer
fetches these via `GET /api/prices` when computing markup floors. The operator
(or agent) updates them via `POST /api/prices`.

Default prices (from PRD-week7 §5.6) are seeded at bootstrap time if not
already present:
  Basic300: 450.00
  Pro450:   800.00
  Elite700: 1400.00
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import Event, EventType, Product, ProductType, WholesalePrice
from app.services.config_service import ConfigService

WHOLESALE_DEFAULTS: dict[str, Decimal] = {
    "Basic300": Decimal("450.00"),
    "Pro450": Decimal("800.00"),
    "Elite700": Decimal("1400.00"),
}

SCHEMA_VERSION = 1


class WholesalePriceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = ConfigService(db)

    def _printers(self) -> list[Product]:
        return (
            self.db.query(Product)
            .filter(Product.type == ProductType.PRINTER)
            .order_by(Product.name)
            .all()
        )

    def ensure_defaults(self) -> None:
        """Seed default wholesale prices if any printer model has no price yet."""

        for product in self._printers():
            existing = (
                self.db.query(WholesalePrice)
                .filter_by(product_id=product.id)
                .one_or_none()
            )
            if existing is None:
                default = WHOLESALE_DEFAULTS.get(product.name, Decimal("0.00"))
                self.db.add(WholesalePrice(product_id=product.id, price=default))
        self.db.flush()

    def list_prices(self) -> dict[str, Decimal]:
        """Return `{model_name: price}` for every printer with a price row."""

        rows = (
            self.db.query(WholesalePrice)
            .join(WholesalePrice.product)
            .order_by(Product.name)
            .all()
        )
        return {row.product.name: row.price for row in rows}

    def get_price(self, product_name: str) -> Decimal:
        product = (
            self.db.query(Product)
            .filter(Product.name == product_name, Product.type == ProductType.PRINTER)
            .one_or_none()
        )
        if product is None:
            raise ValueError(f"No printer model {product_name!r}")
        row = self.db.query(WholesalePrice).filter_by(product_id=product.id).one_or_none()
        if row is None:
            raise ValueError(f"No wholesale price set for {product_name!r}")
        return row.price

    def set_price(self, product_name: str, price: Decimal) -> dict[str, Any]:
        """Create or update the wholesale price for a printer model."""

        if price <= 0:
            raise ValueError("price must be positive")

        product = (
            self.db.query(Product)
            .filter(Product.name == product_name, Product.type == ProductType.PRINTER)
            .one_or_none()
        )
        if product is None:
            raise ValueError(f"No printer model {product_name!r}")

        row = self.db.query(WholesalePrice).filter_by(product_id=product.id).one_or_none()
        previous = str(row.price) if row is not None else None

        if row is None:
            row = WholesalePrice(product_id=product.id, price=price)
            self.db.add(row)
        else:
            row.price = price

        self.db.add(
            Event(
                event_type=EventType.WHOLESALE_PRICE_CHANGED,
                sim_date=self.config.get_sim_date(),
                details={
                    "product_name": product_name,
                    "previous_price": previous,
                    "new_price": str(price),
                },
            )
        )
        self.db.flush()
        return {"product_name": product_name, "price": str(price), "previous_price": previous}
