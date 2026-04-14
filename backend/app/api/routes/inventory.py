from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.schemas.schemas import InventoryLevel, CapacityInfo, ManualAdjust

router = APIRouter()


@router.get("/", response_model=List[InventoryLevel])
def get_inventory(db: Session = Depends(get_db)):
    from app.services.inventory_service import InventoryService
    service = InventoryService(db)
    return service.get_all_inventory()


@router.get("/capacity", response_model=CapacityInfo)
def get_capacity(db: Session = Depends(get_db)):
    from app.services.inventory_service import InventoryService
    service = InventoryService(db)
    return service.get_capacity_info()


@router.post("/manual-adjust", response_model=InventoryLevel)
def manual_adjust_inventory(adjust: ManualAdjust, db: Session = Depends(get_db)):
    from app.services.inventory_service import InventoryService
    from decimal import Decimal
    
    service = InventoryService(db)
    try:
        operation = "add" if adjust.quantity >= 0 else "subtract"
        return service.update_inventory(adjust.product_id, Decimal(str(abs(adjust.quantity))), operation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
