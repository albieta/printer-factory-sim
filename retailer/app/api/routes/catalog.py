from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas.schemas import (
    CatalogEntry,
    CatalogResponse,
    PriceSetRequest,
)
from app.services.catalog_service import CatalogService
from app.services.manufacturer_client import ManufacturerClient, ManufacturerError
from app.services.sim_state_service import SimStateService
from app.services.starter_profile import SCHEMA_VERSION, MINIMUM_MARKUP_PCT
from app.utils.database import get_db
from app.utils.deps import get_manufacturer_client

router = APIRouter()


@router.get("", response_model=CatalogResponse)
def list_catalog(db: Session = Depends(get_db)) -> CatalogResponse:
    entries = CatalogService(db).list_catalog()
    return CatalogResponse(
        schema_version=SCHEMA_VERSION,
        entries=[CatalogEntry.model_validate(e) for e in entries],
    )


@router.put("/{product_name}/price", response_model=CatalogResponse)
def set_price(
    product_name: str,
    payload: PriceSetRequest,
    db: Session = Depends(get_db),
    client: ManufacturerClient = Depends(get_manufacturer_client),
) -> CatalogResponse:
    """Set retail price with validation against the minimum markup floor.

    Uses MINIMUM_MARKUP_PCT for validation to allow the agent flexibility
    in setting prices above the floor based on demand conditions. The agent
    can set any price >= wholesale × (1 + MINIMUM_MARKUP_PCT/100).
    """
    sim_day = SimStateService(db).get_current_day()
    try:
        wholesale = client.get_wholesale_price(product_name)
    except ManufacturerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    service = CatalogService(db)
    try:
        service.set_retail_price(
            product_name,
            payload.retail_price,
            wholesale_price=wholesale,
            markup_pct=MINIMUM_MARKUP_PCT,
            sim_day=sim_day,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    entries = service.list_catalog()
    return CatalogResponse(
        schema_version=SCHEMA_VERSION,
        entries=[CatalogEntry.model_validate(e) for e in entries],
    )
