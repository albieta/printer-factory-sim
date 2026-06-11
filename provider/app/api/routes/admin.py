"""Admin routes for provider state export/import and reset."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from app.models.models import Product, PricingTier, Stock, Order, Event, SimState, OrderStatus, EventType
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
def export_provider_state(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Export all provider data for backup."""
    products = db.query(Product).all()
    pricing_tiers = db.query(PricingTier).all()
    stock = db.query(Stock).all()
    orders = db.query(Order).all()
    events = db.query(Event).all()
    sim_state = db.query(SimState).all()

    return json_ready({
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "lead_time_days": p.lead_time_days,
                "created_at": p.created_at,
            }
            for p in products
        ],
        "pricing_tiers": [
            {
                "id": pt.id,
                "product_id": pt.product_id,
                "min_quantity": pt.min_quantity,
                "unit_price": pt.unit_price,
            }
            for pt in pricing_tiers
        ],
        "stock": [
            {
                "product_id": s.product_id,
                "quantity": s.quantity,
                "last_updated": s.last_updated,
            }
            for s in stock
        ],
        "orders": [
            {
                "id": o.id,
                "buyer": o.buyer,
                "product_id": o.product_id,
                "quantity": o.quantity,
                "unit_price": o.unit_price,
                "total_price": o.total_price,
                "placed_day": o.placed_day,
                "expected_delivery_day": o.expected_delivery_day,
                "shipped_day": o.shipped_day,
                "delivered_day": o.delivered_day,
                "status": o.status,
                "status_reason": o.status_reason,
                "created_at": o.created_at,
            }
            for o in orders
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
def import_provider_state(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Import provider data from backup."""
    try:
        # Clear existing data
        db.query(Event).delete()
        db.query(Order).delete()
        db.query(Stock).delete()
        db.query(PricingTier).delete()
        db.query(Product).delete()
        db.query(SimState).delete()

        # Import products
        product_id_map = {}
        for item in payload.get("products", []):
            product = Product(
                id=item["id"],
                name=item["name"],
                description=item.get("description"),
                lead_time_days=item["lead_time_days"],
                created_at=item.get("created_at"),
            )
            db.add(product)
            product_id_map[item["id"]] = product
            db.flush()

        # Import pricing tiers
        for item in payload.get("pricing_tiers", []):
            db.add(PricingTier(
                id=item["id"],
                product_id=item["product_id"],
                min_quantity=item["min_quantity"],
                unit_price=item["unit_price"],
            ))

        # Import stock
        for item in payload.get("stock", []):
            db.add(Stock(
                product_id=item["product_id"],
                quantity=item["quantity"],
                last_updated=item.get("last_updated"),
            ))

        # Import orders
        for item in payload.get("orders", []):
            db.add(Order(
                id=item["id"],
                buyer=item["buyer"],
                product_id=item["product_id"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total_price=item["total_price"],
                placed_day=item["placed_day"],
                expected_delivery_day=item["expected_delivery_day"],
                shipped_day=item.get("shipped_day"),
                delivered_day=item.get("delivered_day"),
                status=OrderStatus(item["status"]),
                status_reason=item.get("status_reason"),
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
            "message": f"Restored provider data: {len(payload.get('products', []))} products, {len(payload.get('orders', []))} orders, {len(payload.get('events', []))} events",
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/reset/empty")
def reset_to_empty(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Clear all provider data."""
    db.query(Event).delete()
    db.query(Order).delete()
    db.query(Stock).delete()
    db.query(PricingTier).delete()
    db.query(Product).delete()
    db.query(SimState).delete()

    # Set sim_state to day 0
    db.add(SimState(key="current_day", value="0"))
    db.commit()

    return {"success": True, "message": "Provider cleared to empty state"}
