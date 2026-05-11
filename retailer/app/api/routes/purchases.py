from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.models import PurchaseOrder
from app.schemas.schemas import PurchaseOrderCreate, PurchaseOrderOut
from app.services.catalog_service import ModelNotFoundError
from app.services.purchase_service import PurchaseError, PurchaseService
from app.utils.config import RetailerConfig
from app.utils.database import get_db

router = APIRouter()


def _out(po: PurchaseOrder) -> PurchaseOrderOut:
    return PurchaseOrderOut(
        id=po.id,
        model_name=po.catalog_item.model_name,
        quantity=po.quantity,
        unit_price=float(po.unit_price),
        total_price=float(po.total_price),
        placed_day=po.placed_day,
        expected_delivery_day=po.expected_delivery_day,
        delivered_day=po.delivered_day,
        external_order_id=po.external_order_id,
        status=po.status.value,
    )


def _config(request: Request) -> RetailerConfig:
    cfg: RetailerConfig = request.app.state.config
    return cfg


@router.post("", response_model=PurchaseOrderOut, status_code=201)
def create_purchase(
    body: PurchaseOrderCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> PurchaseOrderOut:
    cfg = _config(request)
    svc = PurchaseService(db, cfg.manufacturer.url)
    try:
        po = svc.create(body.model, body.quantity, cfg.name)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PurchaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _out(po)


@router.get("", response_model=list[PurchaseOrderOut])
def list_purchases(db: Session = Depends(get_db)) -> list[PurchaseOrderOut]:
    from app.services.purchase_service import PurchaseService as PS
    # manufacturer_url not needed for list
    pos = db.query(PurchaseOrder).order_by(PurchaseOrder.id.desc()).all()
    return [_out(po) for po in pos]


@router.get("/{order_id}", response_model=PurchaseOrderOut)
def get_purchase(order_id: int, db: Session = Depends(get_db)) -> PurchaseOrderOut:
    po = db.query(PurchaseOrder).filter_by(id=order_id).one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return _out(po)
