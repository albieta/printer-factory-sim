from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.models import CustomerOrderStatus as ModelStatus
from app.schemas.schemas import (
    CustomerOrder,
    CustomerOrderCreate,
    CustomerOrderResponse,
    CustomerOrderStatus,
)
from app.services.customer_order_service import CustomerOrderService
from app.services.sim_state_service import SimStateService
from app.services.starter_profile import SCHEMA_VERSION
from app.utils.database import get_db

router = APIRouter()


@router.post("", response_model=CustomerOrderResponse, status_code=201)
def place_order(
    payload: CustomerOrderCreate,
    db: Session = Depends(get_db),
) -> CustomerOrderResponse:
    sim_day = SimStateService(db).get_current_day()
    service = CustomerOrderService(db)
    try:
        order = service.place_order(
            customer=payload.customer,
            product_name=payload.product_name,
            quantity=payload.quantity,
            sim_day=sim_day,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(order)
    return CustomerOrderResponse(
        schema_version=SCHEMA_VERSION,
        order=CustomerOrder.model_validate(order),
    )


@router.get("", response_model=list[CustomerOrder])
def list_orders(
    status: Optional[CustomerOrderStatus] = None,
    db: Session = Depends(get_db),
) -> list[CustomerOrder]:
    model_status = ModelStatus(status.value) if status is not None else None
    orders = CustomerOrderService(db).list_orders(status=model_status)
    return [CustomerOrder.model_validate(o) for o in orders]


@router.get("/{order_id}", response_model=CustomerOrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)) -> CustomerOrderResponse:
    order = CustomerOrderService(db).get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Customer order not found")
    return CustomerOrderResponse(
        schema_version=SCHEMA_VERSION,
        order=CustomerOrder.model_validate(order),
    )


@router.delete("/{order_id}", response_model=CustomerOrderResponse)
def cancel_order(order_id: int, db: Session = Depends(get_db)) -> CustomerOrderResponse:
    sim_day = SimStateService(db).get_current_day()
    service = CustomerOrderService(db)
    try:
        order = service.cancel_order(order_id, sim_day=sim_day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(order)
    return CustomerOrderResponse(
        schema_version=SCHEMA_VERSION,
        order=CustomerOrder.model_validate(order),
    )
