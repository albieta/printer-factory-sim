from fastapi import APIRouter, Depends, HTTPException
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

    config_service = ConfigService(db)
    sim_date = config_service.get_sim_date()
    service = PurchaseOrderService(db)
    try:
        order = service.create_purchase_order(po, sim_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return service.serialize_purchase_order(order)
