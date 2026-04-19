from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.models import OrderStatus, Product
from app.schemas.schemas import BatchReleaseResponse, BOMRequirements, ManufacturingOrder, ManufacturingOrderDetail, ReleaseRequest
from app.services.order_service import OrderService
from app.utils.database import get_db

router = APIRouter()


@router.get("/mfg", response_model=List[ManufacturingOrder])
def get_manufacturing_orders(status: Optional[str] = Query(None), db: Session = Depends(get_db)):
    service = OrderService(db)

    if status:
        try:
            order_status = OrderStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}") from exc
        orders = service.get_all_orders(order_status)
    else:
        orders = service.get_all_orders()

    return [service.serialize_order(order) for order in orders]


@router.post("/mfg/release", response_model=BatchReleaseResponse)
@router.post("/mfg/release/", response_model=BatchReleaseResponse, include_in_schema=False)
def release_orders(request: ReleaseRequest, db: Session = Depends(get_db)):
    from app.services.config_service import ConfigService

    sim_date = ConfigService(db).get_sim_date()
    return OrderService(db).batch_release_orders(request, sim_date)


@router.post("/mfg/reject", response_model=BatchReleaseResponse)
@router.post("/mfg/reject/", response_model=BatchReleaseResponse, include_in_schema=False)
def reject_orders(request: ReleaseRequest, db: Session = Depends(get_db)):
    from app.services.config_service import ConfigService

    sim_date = ConfigService(db).get_sim_date()
    return OrderService(db).batch_reject_orders(request, sim_date)


@router.get("/mfg/{order_id}", response_model=ManufacturingOrderDetail)
def get_manufacturing_order(order_id: str, db: Session = Depends(get_db)):
    service = OrderService(db)
    order = service.get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    payload = service.serialize_order(order)
    payload["bom_requirements"] = []
    return payload


@router.get("/mfg/{order_id}/requirements", response_model=BOMRequirements)
def get_order_requirements(order_id: str, db: Session = Depends(get_db)):
    service = OrderService(db)
    order = service.get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    bom_entries = service.get_bom_requirements(order.product_id)
    product = db.query(Product).filter(Product.id == order.product_id).first()
    requirements = []

    for bom in bom_entries:
        material = db.query(Product).filter(Product.id == bom.material_id).first()
        requirements.append(
            {
                "material_id": bom.material_id,
                "material_name": material.name if material else "Unknown",
                "quantity_per_unit": float(bom.quantity),
                "total_required": float(bom.quantity * order.quantity),
            }
        )

    return BOMRequirements(product_id=order.product_id, product_name=product.name if product else "Unknown", requirements=requirements)
