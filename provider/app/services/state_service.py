"""JSON import/export helpers for provider state snapshots."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import Event, Order, PricingTier, Product, SimState, Stock
from app.services.starter_profile import SCHEMA_VERSION


class StateService:
    """Serialize and restore provider database state."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def export_state(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of provider state."""

        products = self.db.query(Product).order_by(Product.id).all()
        orders = self.db.query(Order).order_by(Order.id).all()
        events = self.db.query(Event).order_by(Event.id).all()
        sim_state = self.db.query(SimState).order_by(SimState.key).all()

        return {
            "schema_version": SCHEMA_VERSION,
            "sim_state": [{"key": row.key, "value": row.value} for row in sim_state],
            "products": [
                {
                    "id": product.id,
                    "name": product.name,
                    "description": product.description,
                    "lead_time_days": product.lead_time_days,
                    "pricing_tiers": [
                        {
                            "min_quantity": tier.min_quantity,
                            "unit_price": str(tier.unit_price),
                        }
                        for tier in product.pricing_tiers
                    ],
                    "stock_quantity": product.stock.quantity if product.stock else 0,
                }
                for product in products
            ],
            "orders": [
                {
                    "id": order.id,
                    "buyer": order.buyer,
                    "product_id": order.product_id,
                    "quantity": order.quantity,
                    "unit_price": str(order.unit_price),
                    "total_price": str(order.total_price),
                    "placed_day": order.placed_day,
                    "expected_delivery_day": order.expected_delivery_day,
                    "shipped_day": order.shipped_day,
                    "delivered_day": order.delivered_day,
                    "status": order.status.value,
                    "status_reason": order.status_reason,
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                }
                for order in orders
            ],
            "events": [
                {
                    "id": event.id,
                    "event_type": event.event_type.value,
                    "sim_day": event.sim_day,
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                    "details": event.details,
                }
                for event in events
            ],
        }

    def import_state(self, payload: dict[str, Any]) -> None:
        """Replace provider state with a snapshot produced by `export_state`."""

        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version {payload.get('schema_version')!r}; "
                f"expected {SCHEMA_VERSION}"
            )

        self.db.query(Event).delete()
        self.db.query(Order).delete()
        self.db.query(PricingTier).delete()
        self.db.query(Stock).delete()
        self.db.query(Product).delete()
        self.db.query(SimState).delete()
        self.db.flush()

        for entry in payload.get("products", []):
            product = Product(
                id=entry["id"],
                name=entry["name"],
                description=entry.get("description"),
                lead_time_days=entry["lead_time_days"],
            )
            self.db.add(product)
            self.db.flush()
            for tier in entry.get("pricing_tiers", []):
                self.db.add(
                    PricingTier(
                        product_id=product.id,
                        min_quantity=tier["min_quantity"],
                        unit_price=Decimal(str(tier["unit_price"])),
                    )
                )
            self.db.add(Stock(product_id=product.id, quantity=entry.get("stock_quantity", 0)))

        for row in payload.get("sim_state", []):
            self.db.add(SimState(key=row["key"], value=str(row["value"])))

        for entry in payload.get("orders", []):
            self.db.add(
                Order(
                    id=entry["id"],
                    buyer=entry["buyer"],
                    product_id=entry["product_id"],
                    quantity=entry["quantity"],
                    unit_price=Decimal(str(entry["unit_price"])),
                    total_price=Decimal(str(entry["total_price"])),
                    placed_day=entry["placed_day"],
                    expected_delivery_day=entry["expected_delivery_day"],
                    shipped_day=entry.get("shipped_day"),
                    delivered_day=entry.get("delivered_day"),
                    status=entry["status"],
                    status_reason=entry.get("status_reason"),
                )
            )

        for entry in payload.get("events", []):
            self.db.add(
                Event(
                    id=entry["id"],
                    event_type=entry["event_type"],
                    sim_day=entry["sim_day"],
                    entity_type=entry.get("entity_type"),
                    entity_id=entry.get("entity_id"),
                    details=entry.get("details"),
                )
            )

        self.db.commit()
