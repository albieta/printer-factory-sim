from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.utils.database import get_db
from app.schemas.schemas import (
    ManufacturingOrder, ManufacturingOrderDetail,
    ReleaseRequest, BatchReleaseResponse, BOMRequirements
)

router = APIRouter()


@router.get("/mfg", response_model=List[ManufacturingOrder])
def get_manufacturing_orders(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    from app.services.order_service import OrderService
    from app.models.models import OrderStatus
    
    service = OrderService(db)
    
    if status:
        try:
            order_status = OrderStatus(status)
            return service.get_all_orders(order_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    return service.get_all_orders()


@router.get("/mfg/{order_id}", response_model=ManufacturingOrderDetail)
def get_manufacturing_order(order_id: str, db: Session = Depends(get_db)):
    from app.services.order_service import OrderService
    
    service = OrderService(db)
    order = service.get_order_by_id(order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order


@router.get("/mfg/{order_id}/requirements", response_model=BOMRequirements)
def get_order_requirements(order_id: str, db: Session = Depends(get_db)):
    from app.services.order_service import OrderService
    from app.models.models import Product
    
    service = OrderService(db)
    order = service.get_order_by_id(order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    bom_entries = service.get_bom_requirements(order.product_id)
    product = db.query(Product).filter(Product.id == order.product_id).first()
    
    requirements = []
    for bom in bom_entries:
        material = db.query(Product).filter(Product.id == bom.material_id).first()
        requirements.append({
            "material_id": bom.material_id,
            "material_name": material.name if material else "Unknown",
            "quantity_per_unit": float(bom.quantity),
            "total_required": float(bom.quantity * order.quantity)
        })
    
    return BOMRequirements(
        product_id=order.product_id,
        product_name=product.name if product else "Unknown",
        requirements=requirements
    )


@router.post("/mfg/release", response_model=BatchReleaseResponse)
def release_orders(request: ReleaseRequest, db: Session = Depends(get_db)):
    from app.services.order_service import OrderService
    from app.services.config_service import ConfigService
    
    config_service = ConfigService(db)
    sim_date = config_service.get_sim_date()
    
    service = OrderService(db)
    return service.batch_release_orders(request, sim_date)
