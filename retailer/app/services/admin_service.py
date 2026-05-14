"""Retailer admin operations: full-state JSON export and import.

Export serialises every table (catalog, stock, customer orders, purchase
orders, events, sim state) into a single dict.  Import is the reverse
and is *destructive* — it replaces all rows.  The caller is responsible
for confirming the user's intent before calling `import_state`.

The format is versioned (`schema_version`) so future additions can be
handled without breaking existing export files.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import (
    CatalogEntry,
    CustomerOrder,
    CustomerOrderStatus,
    Event,
    EventType,
    PurchaseOrder,
    PurchaseOrderStatus,
    SimState,
    Stock,
)
from app.services.sim_state_service import SimStateService

EXPORT_SCHEMA_VERSION = 1


def _decimal(v: Any) -> str:
    return str(v) if v is not None else "0"


def export_state(db: Session) -> dict[str, Any]:
    """Serialise all retailer state to a plain dict."""

    catalog = [
        {
            "product_name": e.product_name,
            "description": e.description,
            "retail_price": _decimal(e.retail_price),
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in db.query(CatalogEntry).order_by(CatalogEntry.product_name).all()
    ]

    stock = [
        {
            "product_name": s.product_name,
            "quantity": s.quantity,
            "last_updated": s.last_updated.isoformat() if s.last_updated else None,
        }
        for s in db.query(Stock).order_by(Stock.product_name).all()
    ]

    customer_orders = [
        {
            "id": o.id,
            "customer": o.customer,
            "product_name": o.product_name,
            "quantity": o.quantity,
            "unit_price": _decimal(o.unit_price),
            "total_price": _decimal(o.total_price),
            "placed_day": o.placed_day,
            "fulfilled_day": o.fulfilled_day,
            "status": o.status.value,
            "status_reason": o.status_reason,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in db.query(CustomerOrder).order_by(CustomerOrder.id).all()
    ]

    purchase_orders = [
        {
            "id": o.id,
            "manufacturer_name": o.manufacturer_name,
            "product_name": o.product_name,
            "quantity": o.quantity,
            "unit_price": _decimal(o.unit_price),
            "total_price": _decimal(o.total_price),
            "placed_day": o.placed_day,
            "expected_delivery_day": o.expected_delivery_day,
            "delivered_day": o.delivered_day,
            "status": o.status.value,
            "status_reason": o.status_reason,
            "external_order_id": o.external_order_id,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in db.query(PurchaseOrder).order_by(PurchaseOrder.id).all()
    ]

    events = [
        {
            "id": e.id,
            "event_type": e.event_type.value,
            "sim_day": e.sim_day,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "details": e.details,
        }
        for e in db.query(Event).order_by(Event.id).all()
    ]

    current_day = SimStateService(db).get_current_day()

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.utcnow().isoformat(),
        "current_day": current_day,
        "catalog": catalog,
        "stock": stock,
        "customer_orders": customer_orders,
        "purchase_orders": purchase_orders,
        "events": events,
    }


def import_state(db: Session, data: dict[str, Any]) -> None:
    """Replace all retailer state with the contents of `data`.

    Destructive.  The caller must commit after this returns.
    """

    version = data.get("schema_version")
    if version != EXPORT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported export schema_version {version!r}; expected {EXPORT_SCHEMA_VERSION}"
        )

    # Delete all rows in reverse dependency order.
    db.query(Event).delete()
    db.query(PurchaseOrder).delete()
    db.query(CustomerOrder).delete()
    db.query(Stock).delete()
    db.query(CatalogEntry).delete()
    db.query(SimState).delete()
    db.flush()

    # Restore catalog.
    for row in data.get("catalog", []):
        db.add(
            CatalogEntry(
                product_name=row["product_name"],
                description=row.get("description"),
                retail_price=Decimal(row["retail_price"]),
            )
        )

    # Restore stock.
    for row in data.get("stock", []):
        db.add(Stock(product_name=row["product_name"], quantity=int(row["quantity"])))

    # Restore customer orders.
    for row in data.get("customer_orders", []):
        db.add(
            CustomerOrder(
                id=row["id"],
                customer=row["customer"],
                product_name=row["product_name"],
                quantity=row["quantity"],
                unit_price=Decimal(row["unit_price"]),
                total_price=Decimal(row["total_price"]),
                placed_day=row["placed_day"],
                fulfilled_day=row.get("fulfilled_day"),
                status=CustomerOrderStatus(row["status"]),
                status_reason=row.get("status_reason"),
            )
        )

    # Restore purchase orders.
    for row in data.get("purchase_orders", []):
        db.add(
            PurchaseOrder(
                id=row["id"],
                manufacturer_name=row["manufacturer_name"],
                product_name=row["product_name"],
                quantity=row["quantity"],
                unit_price=Decimal(row["unit_price"]),
                total_price=Decimal(row["total_price"]),
                placed_day=row["placed_day"],
                expected_delivery_day=row.get("expected_delivery_day"),
                delivered_day=row.get("delivered_day"),
                status=PurchaseOrderStatus(row["status"]),
                status_reason=row.get("status_reason"),
                external_order_id=row.get("external_order_id"),
            )
        )

    # Restore events.
    for row in data.get("events", []):
        db.add(
            Event(
                id=row["id"],
                event_type=EventType(row["event_type"]),
                sim_day=row["sim_day"],
                entity_type=row.get("entity_type"),
                entity_id=row.get("entity_id"),
                details=row.get("details"),
            )
        )

    # Restore sim state.
    current_day = int(data.get("current_day", 0))
    db.add(SimState(key="current_day", value=str(current_day)))

    db.flush()
