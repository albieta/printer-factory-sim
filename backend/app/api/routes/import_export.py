from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.models.models import BillOfMaterials, Event, ManufacturingOrder, Product, ProductType, PurchaseOrder, Supplier
from app.schemas.schemas import ImportResult
from app.services.config_service import ConfigService
from app.services.inventory_service import InventoryService
from app.services.presentation_service import serialize_manufacturing_order, serialize_purchase_order
from app.utils.database import get_db

router = APIRouter()


def make_attachment_response(payload: dict[str, Any], filename: str) -> JSONResponse:
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value


def serialize_product(product: Product) -> dict[str, Any]:
    return {
        "id": product.id,
        "name": product.name,
        "type": product.type,
        "assembly_hours": product.assembly_hours,
        "created_at": product.created_at,
    }


def serialize_bom_entry(entry: BillOfMaterials) -> dict[str, Any]:
    return {
        "id": entry.id,
        "finished_product_id": entry.finished_product_id,
        "finished_product_name": entry.finished_product.name if entry.finished_product else None,
        "material_id": entry.material_id,
        "material_name": entry.material.name if entry.material else None,
        "quantity": entry.quantity,
    }


def serialize_supplier(supplier: Supplier) -> dict[str, Any]:
    return {
        "id": supplier.id,
        "name": supplier.name,
        "product_id": supplier.product_id,
        "product_name": supplier.product.name if supplier.product else None,
        "unit_cost": supplier.unit_cost,
        "lead_time_days": supplier.lead_time_days,
        "quantity_breaks": supplier.quantity_breaks,
    }


def serialize_event(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "sim_date": event.sim_date,
        "timestamp": event.timestamp,
        "details": event.details or {},
    }


@router.get("/export/full-state/")
def export_full_state(db: Session = Depends(get_db)):
    inventory_service = InventoryService(db)

    products = db.query(Product).order_by(Product.name.asc()).all()
    bom_entries = (
        db.query(BillOfMaterials)
        .options(
            joinedload(BillOfMaterials.finished_product),
            joinedload(BillOfMaterials.material),
        )
        .all()
    )
    suppliers = db.query(Supplier).options(joinedload(Supplier.product)).order_by(Supplier.name.asc()).all()
    manufacturing_orders = (
        db.query(ManufacturingOrder)
        .options(joinedload(ManufacturingOrder.product))
        .order_by(ManufacturingOrder.created_date.asc(), ManufacturingOrder.reference_code.asc())
        .all()
    )
    purchase_orders = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.product), joinedload(PurchaseOrder.supplier))
        .order_by(PurchaseOrder.issue_date.asc(), PurchaseOrder.reference_code.asc())
        .all()
    )
    events = db.query(Event).order_by(Event.timestamp.asc()).all()

    payload = json_ready(
        {
            "config": ConfigService(db).serialize_config(),
            "products": [serialize_product(product) for product in products],
            "bom_entries": [serialize_bom_entry(entry) for entry in bom_entries],
            "suppliers": [serialize_supplier(supplier) for supplier in suppliers],
            "inventory": inventory_service.get_inventory_snapshot(),
            "manufacturing_orders": [serialize_manufacturing_order(order) for order in manufacturing_orders],
            "purchase_orders": [serialize_purchase_order(order) for order in purchase_orders],
            "events": [serialize_event(event) for event in events],
        }
    )

    return make_attachment_response(payload, "simulation_state.json")


@router.get("/export/inventory-only/")
def export_inventory(db: Session = Depends(get_db)):
    products = (
        db.query(Product)
        .filter(Product.type == ProductType.MATERIAL)
        .order_by(Product.name.asc())
        .all()
    )
    payload = json_ready(
        {
            "inventory": InventoryService(db).get_inventory_snapshot(),
            "products": [serialize_product(product) for product in products],
        }
    )
    return make_attachment_response(payload, "inventory_state.json")


@router.get("/export/events-only/")
def export_events(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.timestamp.asc()).all()
    payload = json_ready({"events": [serialize_event(event) for event in events]})
    return make_attachment_response(payload, "events_history.json")


@router.post("/import/full-state/")
async def import_full_state(db: Session = Depends(get_db)):
    # This would require file upload handling
    # For now, return a placeholder
    return ImportResult(
        success=False,
        message="Import functionality requires file upload implementation",
        errors=["Not yet implemented"],
    )
