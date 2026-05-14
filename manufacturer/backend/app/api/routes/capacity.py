"""Capacity info: GET /api/capacity."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.services.config_service import ConfigService
from app.services.inventory_service import InventoryService
from app.utils.database import get_db

router = APIRouter()


@router.get("")
def get_capacity(db: Session = Depends(get_db)) -> dict[str, Any]:
    config_svc = ConfigService(db)
    inv_svc = InventoryService(db)
    capacity = inv_svc.get_capacity_info()
    return {
        "daily_assembly_hours": config_svc.get_effective_daily_assembly_hours(),
        "assembly_lines": config_svc.get_config().assembly_lines,
        "workers_per_line": config_svc.get_config().workers_per_line,
        "shift_hours": config_svc.get_config().shift_hours,
        "warehouse_capacity": capacity["warehouse_capacity"],
        "current_usage": capacity["current_usage"],
        "available_capacity": capacity["available_capacity"],
        "usage_percentage": capacity["usage_percentage"],
    }
