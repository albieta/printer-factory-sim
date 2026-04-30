"""Provider catalogue mutations used by the CLI.

These are operator actions, not buyer-facing order lifecycle operations:
changing a quantity-break price and simulating an upstream restock. Each
change writes an audit event in the same transaction as the mutation.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.models import EventType, PricingTier, Stock
from app.services.catalog_service import CatalogService
from app.services.event_service import EventService
from app.services.sim_state_service import SimStateService


class AdminService:
    """Mutating provider administration operations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.catalog = CatalogService(db)
        self.events = EventService(db)
        self.sim_state = SimStateService(db)

    def set_price(self, product_id: int, min_quantity: int, unit_price: Decimal) -> PricingTier:
        """Create or update one pricing tier for a product."""

        if min_quantity <= 0:
            raise ValueError("min_quantity must be positive")
        if unit_price <= 0:
            raise ValueError("unit_price must be positive")

        product = self.catalog.get_product(product_id)
        if product is None:
            raise ValueError(f"product_id={product_id} not found")

        tier = (
            self.db.query(PricingTier)
            .filter_by(product_id=product_id, min_quantity=min_quantity)
            .one_or_none()
        )
        previous_price = str(tier.unit_price) if tier is not None else None
        if tier is None:
            tier = PricingTier(
                product_id=product_id,
                min_quantity=min_quantity,
                unit_price=unit_price,
            )
            self.db.add(tier)
        else:
            tier.unit_price = unit_price

        self.events.record(
            EventType.PRICE_CHANGED,
            self.sim_state.get_current_day(),
            entity_type="product",
            entity_id=product_id,
            details={
                "product_name": product.name,
                "min_quantity": min_quantity,
                "previous_unit_price": previous_price,
                "unit_price": str(unit_price),
            },
        )
        self.db.commit()
        self.db.refresh(tier)
        return tier

    def restock(self, product_id: int, quantity: int) -> Stock:
        """Increase provider stock for `product_id` by `quantity`."""

        if quantity <= 0:
            raise ValueError("quantity must be positive")

        product = self.catalog.get_product(product_id)
        if product is None:
            raise ValueError(f"product_id={product_id} not found")

        stock = self.catalog.get_stock(product_id)
        if stock is None:
            stock = Stock(product_id=product_id, quantity=0)
            self.db.add(stock)
            self.db.flush()

        previous = stock.quantity
        stock.quantity += quantity
        self.events.record(
            EventType.STOCK_RESTOCKED,
            self.sim_state.get_current_day(),
            entity_type="stock",
            entity_id=product_id,
            details={
                "product_name": product.name,
                "quantity": quantity,
                "previous": previous,
                "current": stock.quantity,
            },
        )
        self.db.commit()
        self.db.refresh(stock)
        return stock
