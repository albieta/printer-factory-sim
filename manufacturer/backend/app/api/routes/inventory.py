from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.schemas.schemas import CapacityInfo, InventoryLevel, ManualAdjust, InventoryAdjustmentLog
from app.utils.database import get_db

router = APIRouter()


@router.get("/", response_model=List[InventoryLevel])
def get_inventory(db: Session = Depends(get_db)):
    from app.services.inventory_service import InventoryService

    return InventoryService(db).get_inventory_snapshot()


@router.get("/adjustment-logs", response_model=List[InventoryAdjustmentLog])
def get_adjustment_logs(db: Session = Depends(get_db)):
    from app.services.inventory_service import InventoryService

    return InventoryService(db).get_adjustment_logs()


@router.get("/capacity", response_model=CapacityInfo)
def get_capacity(db: Session = Depends(get_db)):
    from app.services.inventory_service import InventoryService

    return InventoryService(db).get_capacity_info()


@router.post("/manual-adjust", response_model=InventoryLevel)
def manual_adjust_inventory(adjust: ManualAdjust, db: Session = Depends(get_db)):
    from decimal import Decimal
    from app.services.config_service import ConfigService
    from app.services.inventory_service import InventoryService
    from app.services.order_service import OrderService

    service = InventoryService(db)
    try:
        operation = "add" if adjust.quantity >= 0 else "subtract"
        item = service.update_inventory(adjust.product_id, Decimal(str(abs(adjust.quantity))), operation)
        sim_date = ConfigService(db).get_sim_date()
        OrderService(db).recheck_blocked_orders(sim_date)
        service.log_adjustment(adjust.product_id, adjust.quantity, "ADJUSTED", adjust.reason or "Manual adjustment", sim_date)
        accepted_order_demand = service.get_accepted_order_material_demand()
        pending_inbound_by_material = service.get_pending_inbound_material_quantity()
        return service.serialize_inventory_level(
            item,
            accepted_order_demand.get(item.product_id, 0.0),
            pending_inbound_by_material.get(item.product_id, 0.0),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/trash", response_model=InventoryLevel)
def trash_inventory(adjust: ManualAdjust, db: Session = Depends(get_db)):
    """Delete a specified amount of material from inventory.

    Agents should only use this to clean up useless materials when warehouse
    is under pressure. Trashing reduces warehouse clutter
    and frees space for future operations.

    The quantity parameter specifies how much to trash:
    - Minimum: 1 unit
    - Maximum: current stock (cannot trash more than available)
    - Final stock will be: current_stock - trash_amount (always >= 0)
    """
    from decimal import Decimal
    from app.services.config_service import ConfigService
    from app.services.inventory_service import InventoryService
    from app.services.order_service import OrderService

    service = InventoryService(db)
    try:
        # Get current inventory
        inventory = service.get_inventory_by_product(adjust.product_id)
        current_stock = float(inventory.quantity)
        trash_amount = float(adjust.quantity)

        # Validate trash amount
        if trash_amount < 1:
            raise ValueError(
                f"Cannot trash {adjust.product_id}: minimum trash amount is 1 unit. "
                f"(requested: {trash_amount})"
            )

        if trash_amount > current_stock:
            raise ValueError(
                f"Cannot trash {adjust.product_id}: trash amount ({trash_amount}) exceeds current stock ({current_stock:.1f}). "
                f"Maximum trash: {current_stock:.1f}"
            )

        # Trash the material (subtract the specified amount)
        final_stock = Decimal(str(current_stock - trash_amount))
        item = service.update_inventory(adjust.product_id, final_stock, operation="set")
        sim_date = ConfigService(db).get_sim_date()
        OrderService(db).recheck_blocked_orders(sim_date)
        service.log_adjustment(adjust.product_id, -trash_amount, "TRASHED", adjust.reason or "Material trashed", sim_date)
        accepted_order_demand = service.get_accepted_order_material_demand()
        pending_inbound_by_material = service.get_pending_inbound_material_quantity()
        return service.serialize_inventory_level(
            item,
            accepted_order_demand.get(item.product_id, 0.0),
            pending_inbound_by_material.get(item.product_id, 0.0),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
