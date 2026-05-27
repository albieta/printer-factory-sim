"""Inbound sales-order routes: POST/GET /api/sales/orders."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.models import SalesOrderStatus as ModelStatus
from app.services.sales_order_service import SCHEMA_VERSION, SalesOrderService
from app.utils.database import get_db

router = APIRouter()


class SalesOrderCreate(BaseModel):
    retailer: str = Field(min_length=1)
    model: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class SalesOrderResponse(BaseModel):
    schema_version: int
    order: dict[str, Any]


class SalesOrderReject(BaseModel):
    reason: str = ""


@router.post("", response_model=SalesOrderResponse, status_code=201)
def create_sales_order(
    payload: SalesOrderCreate,
    db: Session = Depends(get_db),
) -> SalesOrderResponse:
    service = SalesOrderService(db)
    try:
        order = service.create_from_retailer(
            retailer_name=payload.retailer,
            product_name=payload.model,
            quantity=payload.quantity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(order)
    return SalesOrderResponse(schema_version=SCHEMA_VERSION, order=service.serialize_order(order))


@router.get("", response_model=list[dict[str, Any]])
def list_sales_orders(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    model_status: Optional[ModelStatus] = None
    if status is not None:
        try:
            model_status = ModelStatus(status.upper())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}") from exc
    service = SalesOrderService(db)
    return [service.serialize_order(o) for o in service.list_orders(status=model_status)]


@router.get("/{order_id}", response_model=SalesOrderResponse)
def get_sales_order(order_id: str, db: Session = Depends(get_db)) -> SalesOrderResponse:
    service = SalesOrderService(db)
    order = service.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Sales order not found")
    return SalesOrderResponse(schema_version=SCHEMA_VERSION, order=service.serialize_order(order))


@router.post("/{order_id}/release", response_model=SalesOrderResponse)
def release_sales_order(order_id: str, db: Session = Depends(get_db)) -> SalesOrderResponse:
    service = SalesOrderService(db)
    result = service.release_to_production(order_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Release failed"))
    db.commit()
    order = service.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Sales order not found after release")
    db.refresh(order)
    return SalesOrderResponse(schema_version=SCHEMA_VERSION, order=service.serialize_order(order))


@router.post("/{order_id}/reject", response_model=SalesOrderResponse)
def reject_sales_order(
    order_id: str,
    payload: SalesOrderReject,
    db: Session = Depends(get_db),
) -> SalesOrderResponse:
    service = SalesOrderService(db)
    result = service.reject_sales_order(order_id, payload.reason)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Reject failed"))
    db.commit()
    order = service.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Sales order not found after reject")
    db.refresh(order)
    return SalesOrderResponse(schema_version=SCHEMA_VERSION, order=service.serialize_order(order))
