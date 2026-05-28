"""Admin routes for retailer state export/import and reset."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from app.models.models import CatalogEntry, Stock, CustomerOrder, PurchaseOrder, Event, SimState, CustomerOrderStatus, PurchaseOrderStatus, EventType
from app.utils.database import get_db

router = APIRouter()


def json_ready(value: Any) -> Any:
    """Convert special types to JSON-serializable formats."""
    from decimal import Decimal
    from datetime import datetime
    from enum import Enum

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value


@router.get("/export/state")
def export_retailer_state(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Export all retailer data for backup."""
    catalog = db.query(CatalogEntry).all()
    stock = db.query(Stock).all()
    customer_orders = db.query(CustomerOrder).all()
    purchase_orders = db.query(PurchaseOrder).all()
    events = db.query(Event).all()
    sim_state = db.query(SimState).all()

    return json_ready({
        "catalog": [
            {
                "product_name": c.product_name,
                "description": c.description,
                "retail_price": c.retail_price,
                "created_at": c.created_at,
            }
            for c in catalog
        ],
        "stock": [
            {
                "product_name": s.product_name,
                "quantity": s.quantity,
                "last_updated": s.last_updated,
            }
            for s in stock
        ],
        "customer_orders": [
            {
                "id": co.id,
                "customer": co.customer,
                "product_name": co.product_name,
                "quantity": co.quantity,
                "unit_price": co.unit_price,
                "total_price": co.total_price,
                "placed_day": co.placed_day,
                "fulfilled_day": co.fulfilled_day,
                "status": co.status,
                "status_reason": co.status_reason,
                "created_at": co.created_at,
            }
            for co in customer_orders
        ],
        "purchase_orders": [
            {
                "id": po.id,
                "manufacturer_name": po.manufacturer_name,
                "product_name": po.product_name,
                "quantity": po.quantity,
                "unit_price": po.unit_price,
                "total_price": po.total_price,
                "placed_day": po.placed_day,
                "expected_delivery_day": po.expected_delivery_day,
                "delivered_day": po.delivered_day,
                "status": po.status,
                "status_reason": po.status_reason,
                "external_order_id": po.external_order_id,
                "created_at": po.created_at,
            }
            for po in purchase_orders
        ],
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "sim_day": e.sim_day,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "timestamp": e.timestamp,
                "details": e.details,
            }
            for e in events
        ],
        "sim_state": {s.key: s.value for s in sim_state},
    })


@router.post("/import/state")
def import_retailer_state(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Import retailer data from backup."""
    try:
        # Clear existing data
        db.query(Event).delete()
        db.query(PurchaseOrder).delete()
        db.query(CustomerOrder).delete()
        db.query(Stock).delete()
        db.query(CatalogEntry).delete()
        db.query(SimState).delete()

        # Import catalog
        for item in payload.get("catalog", []):
            db.add(CatalogEntry(
                product_name=item["product_name"],
                description=item.get("description"),
                retail_price=item["retail_price"],
                created_at=item.get("created_at"),
            ))

        # Import stock
        for item in payload.get("stock", []):
            db.add(Stock(
                product_name=item["product_name"],
                quantity=item["quantity"],
                last_updated=item.get("last_updated"),
            ))

        # Import customer orders
        for item in payload.get("customer_orders", []):
            db.add(CustomerOrder(
                id=item["id"],
                customer=item["customer"],
                product_name=item["product_name"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total_price=item["total_price"],
                placed_day=item["placed_day"],
                fulfilled_day=item.get("fulfilled_day"),
                status=CustomerOrderStatus(item["status"]),
                status_reason=item.get("status_reason"),
                created_at=item.get("created_at"),
            ))

        # Import purchase orders
        for item in payload.get("purchase_orders", []):
            db.add(PurchaseOrder(
                id=item["id"],
                manufacturer_name=item["manufacturer_name"],
                product_name=item["product_name"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total_price=item["total_price"],
                placed_day=item["placed_day"],
                expected_delivery_day=item.get("expected_delivery_day"),
                delivered_day=item.get("delivered_day"),
                status=PurchaseOrderStatus(item["status"]),
                status_reason=item.get("status_reason"),
                external_order_id=item.get("external_order_id"),
                created_at=item.get("created_at"),
            ))

        # Import events
        for item in payload.get("events", []):
            db.add(Event(
                id=item["id"],
                event_type=EventType(item["event_type"]),
                sim_day=item["sim_day"],
                entity_type=item.get("entity_type"),
                entity_id=item.get("entity_id"),
                timestamp=item.get("timestamp"),
                details=item.get("details"),
            ))

        # Import sim state
        for key, value in payload.get("sim_state", {}).items():
            db.add(SimState(key=key, value=str(value)))

        db.commit()
        return {
            "success": True,
            "message": f"Restored retailer data: {len(payload.get('catalog', []))} catalog entries, {len(payload.get('customer_orders', []))} customer orders, {len(payload.get('purchase_orders', []))} purchase orders",
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/reset/empty")
def reset_to_empty(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Clear all retailer data."""
    db.query(Event).delete()
    db.query(PurchaseOrder).delete()
    db.query(CustomerOrder).delete()
    db.query(Stock).delete()
    db.query(CatalogEntry).delete()
    db.query(SimState).delete()

    # Set sim_state to day 0
    db.add(SimState(key="current_day", value="0"))
    db.commit()

    return {"success": True, "message": "Retailer cleared to empty state"}
