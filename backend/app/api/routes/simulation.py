from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.schemas.schemas import SimulationStatus, DayAdvanceResult, ResetConfirm

router = APIRouter()


@router.get("/status", response_model=SimulationStatus)
def get_simulation_status(db: Session = Depends(get_db)):
    from app.services.simulation_service import SimulationService
    service = SimulationService(db)
    status = service.get_simulation_status()
    return status


@router.post("/advance-day", response_model=DayAdvanceResult)
def advance_day(db: Session = Depends(get_db)):
    from app.services.simulation_service import SimulationService
    service = SimulationService(db)
    result = service.advance_day()
    return result


@router.post("/reset", response_model=ResetConfirm)
def reset_simulation(db: Session = Depends(get_db)):
    from app.services.simulation_service import SimulationService
    service = SimulationService(db)
    service.reset_simulation()
    return ResetConfirm(success=True, message="Simulation reset successfully")
