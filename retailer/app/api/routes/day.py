from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas import DayCurrent, DayAdvanceResult
from app.services.day_service import DayService
from app.services.manufacturer_client import ManufacturerClient
from app.services.sim_state_service import SimStateService
from app.utils.database import get_db
from app.utils.deps import get_manufacturer_client

router = APIRouter()


@router.get("/current", response_model=DayCurrent)
def current_day(db: Session = Depends(get_db)) -> DayCurrent:
    return DayCurrent(current_day=SimStateService(db).get_current_day())


@router.post("/advance", response_model=DayAdvanceResult)
def advance_day(
    db: Session = Depends(get_db),
    client: ManufacturerClient = Depends(get_manufacturer_client),
) -> DayAdvanceResult:
    summary = DayService(db, client).advance_day()
    return DayAdvanceResult(
        previous_day=summary["previous_day"],
        current_day=summary["current_day"],
        purchase_orders_delivered=summary["purchase_orders_delivered"],
        backorders_fulfilled=summary["backorders_fulfilled"],
    )
