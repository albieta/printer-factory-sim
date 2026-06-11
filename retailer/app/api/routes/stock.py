from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.models import Stock as StockModel
from app.schemas.schemas import StockLevel, StockResponse
from app.services.starter_profile import SCHEMA_VERSION
from app.utils.database import get_db

router = APIRouter()


@router.get("", response_model=StockResponse)
def list_stock(db: Session = Depends(get_db)) -> StockResponse:
    items = db.query(StockModel).order_by(StockModel.product_name).all()
    return StockResponse(
        schema_version=SCHEMA_VERSION,
        items=[StockLevel.model_validate(s) for s in items],
    )
