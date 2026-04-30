from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas import StockLevel
from app.services.catalog_service import CatalogService
from app.utils.database import get_db

router = APIRouter()


@router.get("", response_model=list[StockLevel])
def get_stock(db: Session = Depends(get_db)) -> list[StockLevel]:
    return [
        StockLevel(
            product_id=row.product_id,
            product_name=row.product.name if row.product else "Unknown",
            quantity=row.quantity,
            last_updated=row.last_updated,
        )
        for row in CatalogService(db).list_stock()
    ]
