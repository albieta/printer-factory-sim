from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.schemas.schemas import PurchaseOrder, PurchaseOrderCreate

router = APIRouter()


@router.get("/purchase", response_model=List[PurchaseOrder])
def get_purchase_orders(db: Session = Depends(get_db)):
    from app.services.supplier_service import PurchaseOrderService
    service = PurchaseOrderService(db)
    return service.get_all_purchase_orders()


@router.post("/purchase", response_model=PurchaseOrder)
def create_purchase_order(po: PurchaseOrderCreate, db: Session = Depends(get_db)):
    from app.services.supplier_service import PurchaseOrderService
    from app.services.config_service import ConfigService
    
    config_service = ConfigService(db)
    sim_date = config_service.get_sim_date()
    
    service = PurchaseOrderService(db)
    return service.create_purchase_order(po, sim_date)
