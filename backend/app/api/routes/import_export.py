from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
import json
from datetime import date, datetime

from app.utils.database import get_db
from app.schemas.schemas import ImportResult

router = APIRouter()


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


@router.get("/api/export/full-state")
def export_full_state(db: Session = Depends(get_db)):
    from app.models.models import (
        Product, BillOfMaterials, Supplier, Inventory,
        ManufacturingOrder, PurchaseOrder, Event, SimulationConfig
    )
    
    # Export all data
    data = {
        "config": db.query(SimulationConfig).first(),
        "products": db.query(Product).all(),
        "bom_entries": db.query(BillOfMaterials).all(),
        "suppliers": db.query(Supplier).all(),
        "inventory": db.query(Inventory).all(),
        "manufacturing_orders": db.query(ManufacturingOrder).all(),
        "purchase_orders": db.query(PurchaseOrder).all(),
        "events": db.query(Event).all()
    }
    
    return JSONResponse(
        content=json.loads(json.dumps(data, cls=DateTimeEncoder)),
        headers={"Content-Disposition": "attachment; filename=simulation_state.json"}
    )


@router.get("/api/export/inventory-only")
def export_inventory(db: Session = Depends(get_db)):
    from app.models.models import Inventory, Product
    
    inventory = db.query(Inventory).all()
    products = db.query(Product).all()
    
    data = {
        "inventory": inventory,
        "products": products
    }
    
    return JSONResponse(
        content=json.loads(json.dumps(data, cls=DateTimeEncoder)),
        headers={"Content-Disposition": "attachment; filename=inventory_state.json"}
    )


@router.get("/api/export/events-only")
def export_events(db: Session = Depends(get_db)):
    from app.models.models import Event
    
    events = db.query(Event).all()
    
    return JSONResponse(
        content=json.loads(json.dumps({"events": events}, cls=DateTimeEncoder)),
        headers={"Content-Disposition": "attachment; filename=events_history.json"}
    )


@router.post("/api/import/full-state")
async def import_full_state(db: Session = Depends(get_db)):
    # This would require file upload handling
    # For now, return a placeholder
    return ImportResult(
        success=False,
        message="Import functionality requires file upload implementation",
        errors=["Not yet implemented"]
    )
