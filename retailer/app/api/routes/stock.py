from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas import StockItemOut
from app.services.stock_service import StockService
from app.utils.database import get_db

router = APIRouter()


@router.get("", response_model=list[StockItemOut])
def get_stock(db: Session = Depends(get_db)) -> list[StockItemOut]:
    rows = StockService(db).list_stock()
    return [
        StockItemOut(
            model_name=item.model_name,
            quantity=s.quantity if s is not None else 0,
        )
        for item, s in rows
    ]
