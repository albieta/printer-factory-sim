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
    cfg = config_svc.get_config()
    capacity = inv_svc.get_capacity_info()
    return {
        "daily_assembly_hours": config_svc.get_effective_daily_assembly_hours(),
        "assembly_lines": cfg.assembly_lines,
        "workers_per_line": cfg.workers_per_line,
        "shift_hours": cfg.shift_hours,
        "max_workers_per_line": cfg.max_workers_per_line,
        "cost_per_worker_per_hour": float(cfg.cost_per_worker_per_hour or 50),
        "cost_per_assembly_line": float(cfg.cost_per_assembly_line or 50000),
        "warehouse_capacity": capacity["warehouse_capacity"],
        "current_usage": capacity["current_usage"],
        "available_capacity": capacity["available_capacity"],
        "usage_percentage": capacity["usage_percentage"],
    }
