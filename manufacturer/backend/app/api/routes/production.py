"""Production management routes: release and status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.sales_order_service import SalesOrderService
from app.utils.database import get_db

router = APIRouter()


class ReleaseRequest(BaseModel):
    order_id: str


@router.post("/release")
def release_to_production(
    payload: ReleaseRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = SalesOrderService(db)
    result = service.release_to_production(payload.order_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Release failed"))
    db.commit()
    order = result["order"]
    return {
        "success": True,
        "order_id": order.id,
        "reference_code": order.reference_code,
        "status": order.status.value,
        "mfg_order_id": result["mfg_order_id"],
    }


@router.get("/status")
def production_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    orders = SalesOrderService(db).get_production_status()
    return {"active_orders": orders, "count": len(orders)}
