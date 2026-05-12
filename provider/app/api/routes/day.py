from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas import DayAdvanceResult, DayCurrent
from app.services.day_service import DayService
from app.services.sim_state_service import SimStateService
from app.utils.database import get_db

router = APIRouter()


@router.post("/advance", response_model=DayAdvanceResult)
def advance_day(db: Session = Depends(get_db)) -> dict[str, int]:
    return DayService(db).advance()


@router.get("/current", response_model=DayCurrent)
def current_day(db: Session = Depends(get_db)) -> DayCurrent:
    return DayCurrent(current_day=SimStateService(db).get_current_day())
