"""Wholesale price routes: GET/POST /api/prices."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.wholesale_price_service import WholesalePriceService
from app.utils.database import get_db

router = APIRouter()


class PriceSetRequest(BaseModel):
    model: str
    price: str  # accept as string to avoid float precision loss


@router.get("")
def list_prices(db: Session = Depends(get_db)) -> dict[str, Any]:
    prices = WholesalePriceService(db).list_prices()
    return {"prices": {name: str(p) for name, p in prices.items()}}


@router.post("")
def set_price(
    payload: PriceSetRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        price = Decimal(payload.price)
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail=f"Invalid price: {payload.price}") from exc

    service = WholesalePriceService(db)
    try:
        result = service.set_price(payload.model, price)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result
