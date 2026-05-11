from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.schemas.schemas import DayAdvanceOut, DayCurrentOut
from app.services.day_service import DayService
from app.services.sim_state_service import SimStateService
from app.utils.config import RetailerConfig
from app.utils.database import get_db

router = APIRouter()


def _config(request: Request) -> RetailerConfig:
    cfg: RetailerConfig = request.app.state.config
    return cfg


@router.post("/advance", response_model=DayAdvanceOut)
def advance_day(request: Request, db: Session = Depends(get_db)) -> DayAdvanceOut:
    cfg = _config(request)
    result = DayService(db, cfg.manufacturer.url).advance()
    return DayAdvanceOut(**result.as_dict())


@router.get("/current", response_model=DayCurrentOut)
def current_day(db: Session = Depends(get_db)) -> DayCurrentOut:
    day = SimStateService(db).get_current_day()
    return DayCurrentOut(current_day=day)
