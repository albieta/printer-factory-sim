"""Sales API — manufacturer sells finished printers to the retailer.

All routes are mounted under /api/sales by the router aggregator.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas.schemas import (
    SalesOrderCreate,
    SalesOrderOut,
    SalesOrderStatus,
    WholesalePriceOut,
    WholesalePriceSet,
)
from app.services.sales_service import ModelNotFoundError, NoPriceSetError, SalesError, SalesService
from app.utils.database import get_db

router = APIRouter()


def _order_out(order: object, model_name: str) -> SalesOrderOut:
    from app.models.models import SalesOrder as SalesOrderModel
    assert isinstance(order, SalesOrderModel)
    return SalesOrderOut(
        id=order.id,
        model_name=model_name,
        quantity=order.quantity,
        buyer_name=order.buyer_name,
        unit_price=float(order.unit_price),
        total_price=float(order.total_price),
        placed_day=order.placed_day,
        expected_delivery_day=order.expected_delivery_day,
        delivered_day=order.delivered_day,
        status=SalesOrderStatus(order.status.value),
    )


@router.post("/orders", status_code=201)
def create_sales_order(
    body: SalesOrderCreate,
    db: Session = Depends(get_db),
) -> SalesOrderOut:
    """Retailer places a purchase order for finished printers."""
    svc = SalesService(db)
    try:
        order = svc.create_order(body.model_name, body.quantity, body.buyer_name)
        db.commit()
        db.refresh(order)
        model_name = order.product.name
    except NoPriceSetError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SalesError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _order_out(order, model_name)


@router.get("/orders")
def list_sales_orders(db: Session = Depends(get_db)) -> list[SalesOrderOut]:
    """List all sales orders placed by retailers."""
    svc = SalesService(db)
    orders = svc.list_orders()
    return [_order_out(o, o.product.name) for o in orders]


@router.get("/orders/{order_id}")
def get_sales_order(
    order_id: int,
    db: Session = Depends(get_db),
) -> SalesOrderOut:
    """Get a single sales order by ID."""
    order = SalesService(db).get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Sales order {order_id} not found")
    return _order_out(order, order.product.name)


@router.get("/prices")
def list_wholesale_prices(db: Session = Depends(get_db)) -> list[WholesalePriceOut]:
    """List current wholesale prices for all printer models."""
    wps = SalesService(db).list_prices()
    return [
        WholesalePriceOut(
            model_name=wp.product.name,
            price=float(wp.price),
            lead_time_days=wp.lead_time_days,
        )
        for wp in wps
    ]


@router.put("/prices/{model_name}")
def set_wholesale_price(
    model_name: str,
    body: WholesalePriceSet,
    db: Session = Depends(get_db),
) -> WholesalePriceOut:
    """Set the wholesale price for a printer model."""
    svc = SalesService(db)
    try:
        wp = svc.set_price(model_name, Decimal(str(body.price)), body.lead_time_days)
        db.commit()
        db.refresh(wp)
        name = wp.product.name
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return WholesalePriceOut(
        model_name=name,
        price=float(wp.price),
        lead_time_days=wp.lead_time_days,
    )
