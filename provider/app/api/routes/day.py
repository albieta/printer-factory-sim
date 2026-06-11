from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas import (
    DayAdvanceResult,
    DayCurrent,
    MarketSignalResponse,
    MarketSignalUpdate,
)
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


@router.post("/signal", response_model=MarketSignalResponse)
def set_market_signal(
    payload: MarketSignalUpdate,
    db: Session = Depends(get_db),
) -> MarketSignalResponse:
    service = SimStateService(db)
    service.set_market_signal(
        supply_modifier=payload.supply_modifier,
        lead_time_modifier=payload.lead_time_modifier,
    )
    db.commit()
    return MarketSignalResponse(
        supply_modifier=payload.supply_modifier,
        lead_time_modifier=service.get_lead_time_modifier(),
    )


@router.post("/reset")
def reset_provider(db: Session = Depends(get_db)) -> dict[str, str]:
    """Reset provider database to seed data state."""
    import sys
    from pathlib import Path
    from app.utils.database import engine, Base

    # Clear all tables and reload from seed
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Reload seed data
    scripts_path = Path(__file__).parent.parent.parent.parent / "scripts"
    sys.path.insert(0, str(scripts_path))
    from seed_data import seed_database
    seed_database()

    return {"message": "Provider reset to seed data state."}
