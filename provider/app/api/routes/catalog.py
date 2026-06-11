from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.models import Product as ProductModel
from app.schemas.schemas import CatalogResponse, Product
from app.services.admin_service import AdminService
from app.services.catalog_service import CatalogService
from app.services.starter_profile import SCHEMA_VERSION
from app.utils.database import get_db

router = APIRouter()


def serialize_product(product: ProductModel) -> dict[str, Any]:
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "lead_time_days": product.lead_time_days,
        "pricing_tiers": product.pricing_tiers,
        "stock_quantity": product.stock.quantity if product.stock else 0,
    }


@router.get("", response_model=CatalogResponse)
def get_catalog(db: Session = Depends(get_db)) -> CatalogResponse:
    service = CatalogService(db)
    return CatalogResponse(
        schema_version=SCHEMA_VERSION,
        products=[Product(**serialize_product(product)) for product in service.list_products()],
    )


class PriceSetRequest(BaseModel):
    min_quantity: int
    unit_price: str  # accept as string to avoid float precision loss


@router.patch("/{product_name}/price")
def set_tier_price(
    product_name: str,
    payload: PriceSetRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    catalog = CatalogService(db)
    product = catalog.get_product_by_name(product_name)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product not found: {product_name}")
    try:
        price = Decimal(payload.unit_price)
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail=f"Invalid price: {payload.unit_price}") from exc
    try:
        tier = AdminService(db).set_price(product.id, payload.min_quantity, price)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "product_name": product_name,
        "min_quantity": tier.min_quantity,
        "unit_price": str(tier.unit_price),
    }
