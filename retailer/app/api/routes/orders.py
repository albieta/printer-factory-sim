from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.models import CustomerOrder, CustomerOrderStatus
from app.schemas.schemas import CustomerOrderCreate, CustomerOrderOut
from app.services.catalog_service import ModelNotFoundError
from app.services.order_service import OrderError, OrderService
from app.utils.database import get_db

router = APIRouter()


def _out(order: CustomerOrder) -> CustomerOrderOut:
    return CustomerOrderOut(
        id=order.id,
        model_name=order.catalog_item.model_name,
        quantity=order.quantity,
        unit_price=float(order.unit_price),
        total_price=float(order.total_price),
        placed_day=order.placed_day,
        fulfilled_day=order.fulfilled_day,
        status=order.status.value,
    )


@router.post("", response_model=CustomerOrderOut, status_code=201)
def place_order(body: CustomerOrderCreate, db: Session = Depends(get_db)) -> CustomerOrderOut:
    svc = OrderService(db)
    try:
        order = svc.place_order(body.model, body.quantity)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OrderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _out(order)


@router.get("", response_model=list[CustomerOrderOut])
def list_orders(
    status: Optional[str] = None, db: Session = Depends(get_db)
) -> list[CustomerOrderOut]:
    model_status: Optional[CustomerOrderStatus] = None
    if status is not None:
        try:
            model_status = CustomerOrderStatus(status.upper())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"unknown status {status!r}") from exc
    svc = OrderService(db)
    return [_out(o) for o in svc.list_orders(status=model_status)]


@router.get("/{order_id}", response_model=CustomerOrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)) -> CustomerOrderOut:
    order = OrderService(db).get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return _out(order)
