from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.models import Order as OrderModel
from app.models.models import OrderStatus as ModelOrderStatus
from app.schemas.schemas import Order, OrderCreate, OrderResponse, OrderStatus
from app.services.order_service import OrderError, OrderService, ProductNotFoundError
from app.services.starter_profile import SCHEMA_VERSION
from app.utils.database import get_db

router = APIRouter()


def serialize_order(order: OrderModel) -> dict[str, Any]:
    return {
        "id": order.id,
        "buyer": order.buyer,
        "product_id": order.product_id,
        "product_name": order.product.name if getattr(order, "product", None) else None,
        "quantity": order.quantity,
        "unit_price": order.unit_price,
        "total_price": order.total_price,
        "placed_day": order.placed_day,
        "expected_delivery_day": order.expected_delivery_day,
        "shipped_day": order.shipped_day,
        "delivered_day": order.delivered_day,
        "status": order.status,
        "status_reason": order.status_reason,
        "created_at": order.created_at,
    }


@router.post("", response_model=OrderResponse, status_code=201)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)) -> OrderResponse:
    service = OrderService(db)
    try:
        order = service.create_order(
            buyer=payload.buyer,
            product_id=payload.product_id,
            quantity=payload.quantity,
        )
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OrderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return OrderResponse(
        schema_version=SCHEMA_VERSION,
        order=Order(**serialize_order(order)),
    )


@router.get("", response_model=list[Order])
def list_orders(
    status: OrderStatus | None = None,
    db: Session = Depends(get_db),
) -> list[Order]:
    model_status = ModelOrderStatus(status.value) if status is not None else None
    service = OrderService(db)
    return [Order(**serialize_order(order)) for order in service.list_orders(status=model_status)]


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)) -> OrderResponse:
    order = OrderService(db).get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return OrderResponse(
        schema_version=SCHEMA_VERSION,
        order=Order(**serialize_order(order)),
    )
