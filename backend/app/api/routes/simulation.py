from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas import DayAdvanceResult, ResetConfirm, SimulationStatus
from app.services.simulation_service import SimulationService
from app.utils.database import get_db

router = APIRouter()


@router.get("/status", response_model=SimulationStatus)
def get_simulation_status(db: Session = Depends(get_db)):
    return SimulationService(db).get_simulation_status()


@router.post("/advance-day", response_model=DayAdvanceResult)
def advance_day(db: Session = Depends(get_db)):
    return SimulationService(db).advance_day()


@router.post("/reset", response_model=ResetConfirm)
def reset_simulation(db: Session = Depends(get_db)):
    SimulationService(db).reset_simulation()
    return ResetConfirm(success=True, message="Simulation reset to the starter scenario successfully")
