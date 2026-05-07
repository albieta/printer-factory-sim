from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from typing import Any

from app.models.models import Product as ProductModel
from app.schemas.schemas import CatalogResponse, Product
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
