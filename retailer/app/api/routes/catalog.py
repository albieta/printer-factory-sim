from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.schemas.schemas import CatalogItemOut, PriceSetRequest
from app.services.catalog_service import CatalogError, CatalogService, ModelNotFoundError
from app.utils.database import get_db

router = APIRouter()


@router.get("", response_model=list[CatalogItemOut])
def list_catalog(db: Session = Depends(get_db)) -> list[CatalogItemOut]:
    items = CatalogService(db).list_items()
    return [CatalogItemOut(model_name=i.model_name, retail_price=float(i.retail_price)) for i in items]


@router.put("/{model_name}/price", response_model=CatalogItemOut)
def set_price(
    model_name: str,
    body: PriceSetRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> CatalogItemOut:
    from decimal import Decimal
    from app.utils.config import RetailerConfig
    cfg: RetailerConfig = request.app.state.config
    svc = CatalogService(db)
    try:
        item = svc.set_price(model_name, Decimal(str(body.price)), cfg.manufacturer.url)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return CatalogItemOut(model_name=item.model_name, retail_price=float(item.retail_price))
