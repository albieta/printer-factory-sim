from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.models import PurchaseOrderStatus as ModelStatus
from app.schemas.schemas import (
    PurchaseOrder,
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderStatus,
)
from app.services.manufacturer_client import ManufacturerClient, ManufacturerError
from app.services.purchase_order_service import PurchaseOrderService
from app.services.sim_state_service import SimStateService
from app.services.starter_profile import SCHEMA_VERSION
from app.utils.database import get_db
from app.utils.deps import (
    get_manufacturer_client,
    get_manufacturer_name,
    get_retailer_name,
)

router = APIRouter()


@router.post("", response_model=PurchaseOrderResponse, status_code=201)
def place_purchase(
    payload: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    client: ManufacturerClient = Depends(get_manufacturer_client),
    retailer_name: str = Depends(get_retailer_name),
    manufacturer_name: str = Depends(get_manufacturer_name),
) -> PurchaseOrderResponse:
    sim_day = SimStateService(db).get_current_day()
    service = PurchaseOrderService(db, client)
    try:
        order = service.place_purchase_order(
            retailer_name=retailer_name,
            manufacturer_name=manufacturer_name,
            product_name=payload.product_name,
            quantity=payload.quantity,
            sim_day=sim_day,
        )
    except (ValueError, ManufacturerError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(order)
    return PurchaseOrderResponse(
        schema_version=SCHEMA_VERSION,
        order=PurchaseOrder.model_validate(order),
    )


@router.get("", response_model=list[PurchaseOrder])
def list_purchases(
    status: Optional[PurchaseOrderStatus] = None,
    db: Session = Depends(get_db),
    client: ManufacturerClient = Depends(get_manufacturer_client),
) -> list[PurchaseOrder]:
    model_status = ModelStatus(status.value) if status is not None else None
    orders = PurchaseOrderService(db, client).list_orders(status=model_status)
    return [PurchaseOrder.model_validate(o) for o in orders]


@router.get("/{order_id}", response_model=PurchaseOrderResponse)
def get_purchase(
    order_id: int,
    db: Session = Depends(get_db),
    client: ManufacturerClient = Depends(get_manufacturer_client),
) -> PurchaseOrderResponse:
    order = PurchaseOrderService(db, client).get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return PurchaseOrderResponse(
        schema_version=SCHEMA_VERSION,
        order=PurchaseOrder.model_validate(order),
    )
