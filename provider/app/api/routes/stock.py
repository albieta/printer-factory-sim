from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.schemas.schemas import StockLevel
from app.services.admin_service import AdminService
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


class RestockRequest(BaseModel):
    product_name: str
    quantity: int


@router.post("/restock")
def restock_product(payload: RestockRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    catalog = CatalogService(db)
    product = catalog.get_product_by_name(payload.product_name)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product not found: {payload.product_name}")
    try:
        stock = AdminService(db).restock(product.id, payload.quantity)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"product_name": payload.product_name, "new_quantity": stock.quantity}
