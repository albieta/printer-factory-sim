from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.schemas.schemas import PurchaseOrder, PurchaseOrderCreate
from app.services.supplier_service import PurchaseOrderService
from app.utils.database import get_db

router = APIRouter()


@router.get("/", response_model=List[PurchaseOrder])
def get_purchase_orders(db: Session = Depends(get_db)):
    service = PurchaseOrderService(db)
    return [service.serialize_purchase_order(order) for order in service.get_all_purchase_orders()]


@router.post("/", response_model=PurchaseOrder)
def create_purchase_order(po: PurchaseOrderCreate, db: Session = Depends(get_db)):
    from app.services.config_service import ConfigService

    sim_date = ConfigService(db).get_sim_date()
    service = PurchaseOrderService(db)
    order = service.create_purchase_order(po, sim_date)
    return service.serialize_purchase_order(order)
