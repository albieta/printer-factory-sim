from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.schemas.schemas import CapacityInfo, InventoryLevel, ManualAdjust
from app.utils.database import get_db

router = APIRouter()


@router.get("/", response_model=List[InventoryLevel])
def get_inventory(db: Session = Depends(get_db)):
    from app.services.inventory_service import InventoryService

    service = InventoryService(db)
    accepted_order_demand = service.get_accepted_order_material_demand()
    return [
        service.serialize_inventory_level(item, accepted_order_demand.get(item.product_id, 0.0))
        for item in service.get_all_inventory()
    ]


@router.get("/capacity", response_model=CapacityInfo)
def get_capacity(db: Session = Depends(get_db)):
    from app.services.inventory_service import InventoryService

    return InventoryService(db).get_capacity_info()


@router.post("/manual-adjust", response_model=InventoryLevel)
def manual_adjust_inventory(adjust: ManualAdjust, db: Session = Depends(get_db)):
    from decimal import Decimal
    from app.services.config_service import ConfigService
    from app.services.inventory_service import InventoryService
    from app.services.order_service import OrderService

    service = InventoryService(db)
    try:
        operation = "add" if adjust.quantity >= 0 else "subtract"
        item = service.update_inventory(adjust.product_id, Decimal(str(abs(adjust.quantity))), operation)
        sim_date = ConfigService(db).get_sim_date()
        OrderService(db).recheck_blocked_orders(sim_date)
        accepted_order_demand = service.get_accepted_order_material_demand()
        return service.serialize_inventory_level(item, accepted_order_demand.get(item.product_id, 0.0))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
