from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.schemas.schemas import PurchaseOrder, PurchaseOrderCreate
from app.services.supplier_service import PurchaseOrderService
from app.services.financial_service import FinancialService
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
    config = config_service.get_config()
    service = PurchaseOrderService(db)
    try:
        order = service.create_purchase_order(po, sim_date)
        total_cost = float(order.quantity * order.unit_cost)
        financial_service = FinancialService(db)
        product_name = order.product.name if order.product else f"Product {order.product_id}"
        financial_service.record_materials_purchased(
            config.sim_day,
            total_cost,
            f"Purchased {order.quantity} {product_name} from {order.supplier.name}"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return service.serialize_purchase_order(order)
