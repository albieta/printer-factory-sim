"""Read-only views over the provider's catalogue and stock.

The catalogue is the public face of the provider: products, their
quantity-break pricing tiers, and current on-hand stock. Mutating
operations live in `order_service` and `day_service`; this module is
intentionally side-effect-free.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Product, Stock


class CatalogService:
    """Read-only access to products and stock."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_products(self) -> list[Product]:
        """Return all products ordered by name (with eager pricing tiers)."""

        return self.db.query(Product).order_by(Product.name).all()

    def get_product(self, product_id: int) -> Optional[Product]:
        """Return one product by id, or `None` if it does not exist."""

        return self.db.query(Product).filter_by(id=product_id).one_or_none()

    def get_product_by_name(self, name: str) -> Optional[Product]:
        """Return one product by exact name, or `None`.

        Useful for the manufacturer-side bridge, which knows materials by
        their human-readable BOM name rather than by the provider's id.
        """

        return self.db.query(Product).filter_by(name=name).one_or_none()

    def list_stock(self) -> list[Stock]:
        """Return current stock rows for every product."""

        return self.db.query(Stock).all()

    def get_stock(self, product_id: int) -> Optional[Stock]:
        """Return the stock row for a product, or `None`."""

        return self.db.query(Stock).filter_by(product_id=product_id).one_or_none()
