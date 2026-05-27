from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
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


@router.post("/advance-all")
def advance_all(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Advance all three services (retailer → manufacturer → providers) in order."""
    return SimulationService(db).advance_all_services()


@router.post("/reset/", response_model=ResetConfirm)
def reset_simulation(db: Session = Depends(get_db)):
    SimulationService(db).reset_simulation()
    return ResetConfirm(success=True, message="Simulation reset to the starter scenario successfully")


@router.post("/reset-empty/", response_model=ResetConfirm)
def reset_to_empty(db: Session = Depends(get_db)):
    SimulationService(db).reset_to_empty()
    return ResetConfirm(success=True, message="Simulation cleared to empty state. All products, suppliers, and data removed.")


@router.post("/reset-default-config/", response_model=ResetConfirm)
def reset_to_default_config(db: Session = Depends(get_db)):
    import os
    import httpx

    SimulationService(db).reset_to_default_config()

    # Also reset provider and retailer databases
    provider_url = os.getenv("PROVIDER_URL", "http://localhost:8001")
    retailer_url = os.getenv("RETAILER_URL", "http://localhost:8003")

    try:
        with httpx.Client(timeout=10.0) as client:
            # Reset provider (if endpoint exists)
            try:
                client.post(f"{provider_url}/api/day/reset", json={})
            except (httpx.HTTPError, Exception):
                pass  # Provider reset endpoint may not exist yet

            # Reset retailer (if endpoint exists)
            try:
                client.post(f"{retailer_url}/api/day/reset", json={})
            except (httpx.HTTPError, Exception):
                pass  # Retailer reset endpoint may not exist yet
    except Exception:
        pass  # Network errors are non-critical for reset

    return ResetConfirm(success=True, message="Simulation reset to default prefilled demo configuration. All apps cleared.")


@router.get("/orders-daily")
def get_orders_daily(day: int = Query(..., description="Engine day number (1-based)"), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return combined MFG + SalesOrder activity counts for a given sim day.

    Used by engine/metrics.py to populate the daily sales order activity chart.
    """
    from app.models.models import ManufacturingOrder, OrderStatus, Event, EventType, SalesOrder
    from app.services.config_service import ConfigService

    cfg = ConfigService(db).get_config()
    sim_day = cfg.sim_day or 0
    target_date = cfg.sim_date - timedelta(days=max(0, sim_day - day))

    # MFG orders created today (by demand generation during advance_day)
    mfg_created = db.query(ManufacturingOrder).filter(
        ManufacturingOrder.created_date == target_date
    ).count()

    # MFG orders released/accepted today (planner queue or auto-release)
    mfg_released = db.query(ManufacturingOrder).filter(
        ManufacturingOrder.released_date == target_date
    ).count()

    # MFG orders newly blocked today (created today and currently blocked)
    mfg_blocked = db.query(ManufacturingOrder).filter(
        ManufacturingOrder.created_date == target_date,
        ManufacturingOrder.status == OrderStatus.BLOCKED,
    ).count()

    # SalesOrders confirmed/accepted today via SALES_ORDER_RELEASED event
    so_confirmed = db.query(Event).filter(
        Event.event_type == EventType.SALES_ORDER_RELEASED,
        Event.sim_date == target_date,
    ).count()

    # SalesOrders rejected today via SALES_ORDER_REJECTED event
    so_rejected = db.query(Event).filter(
        Event.event_type == EventType.SALES_ORDER_REJECTED,
        Event.sim_date == target_date,
    ).count()

    return {
        "sim_day": day,
        "sim_date": target_date.isoformat(),
        "mfg_created": mfg_created,
        "mfg_released": mfg_released,
        "mfg_blocked": mfg_blocked,
        "so_confirmed": so_confirmed,
        "so_rejected": so_rejected,
    }
