"""REST endpoints for financial management and reporting."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas import FinancialSummary, SimulationConfig, SimulationConfigUpdate
from app.services.config_service import ConfigService
from app.services.financial_service import FinancialService
from app.utils.database import get_db

router = APIRouter()


@router.get("/summary", response_model=FinancialSummary)
def get_financial_summary(db: Session = Depends(get_db)):
    """Get current financial status: costs, revenue, profit."""
    service = FinancialService(db)
    return service.get_financial_summary()


@router.get("/config", response_model=SimulationConfig)
def get_financial_config(db: Session = Depends(get_db)):
    """Get financial configuration: costs and revenue settings."""
    service = ConfigService(db)
    return service.serialize_config()


@router.put("/config", response_model=SimulationConfig)
def update_financial_config(config_update: SimulationConfigUpdate, db: Session = Depends(get_db)):
    """Update financial configuration (costs, etc)."""
    service = ConfigService(db)
    service.update_config(config_update)
    return service.serialize_config()


@router.get("/transactions", response_model=list[dict[str, Any]])
def get_transactions(day: int | None = None, db: Session = Depends(get_db)):
    """Get all financial transactions, optionally filtered by day."""
    service = FinancialService(db)
    return service.get_transactions(day)
