"""State snapshot endpoint — all data needed for agent decision-making in one call."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.utils.database import SessionLocal

router = APIRouter(prefix="/state", tags=["state"])


def get_db() -> Session:
    """Get database session."""
    return SessionLocal()


@router.get("/all", response_model=dict[str, Any])
def get_all_state(session: Session = Depends(get_db)) -> dict[str, Any]:
    """Return all state needed for agent decision-making in a single call.

    Falls back gracefully if unable to fetch complete state.
    """
    try:
        from app.models.models import (
            SimulationConfig, Inventory, ManufacturingOrder, OrderStatus,
            SalesOrder, PurchaseOrder, PurchaseOrderStatus, Product, WholesalePrice
        )

        # Get simulation date
        sim_config = session.query(SimulationConfig).first()
        sim_date = sim_config.sim_date if sim_config else "unknown"

        # Get all inventory
        inventory_dict = {}
        try:
            inventory_rows = session.query(Inventory).all()
            for row in inventory_rows:
                if row.product:
                    inventory_dict[row.product.name] = float(row.quantity or 0)
        except Exception:
            pass

        # Get all products and their wholesale prices
        product_dict = {}
        try:
            products = session.query(Product).all()
            for p in products:
                price_row = session.query(WholesalePrice).filter(
                    WholesalePrice.product_id == p.id
                ).first()
                product_dict[p.name] = {
                    "id": p.id,
                    "price": float(price_row.price or 0) if price_row else 0.0
                }
        except Exception:
            pass

        # Get pending sales orders
        pending_orders = []
        try:
            pending_rows = session.query(SalesOrder).filter(
                SalesOrder.status == "PENDING"
            ).all()
            for order in pending_rows:
                if order.product:
                    pending_orders.append({
                        "id": order.reference_code or order.id,
                        "model": order.product.name,
                        "quantity": order.quantity,
                        "placed_day": order.placed_day,
                    })
        except Exception:
            pass

        # Get assembly queue (released manufacturing orders)
        assembly_queue_count = 0
        assembly_queue_hours = 0.0
        try:
            released_orders = session.query(ManufacturingOrder).filter(
                ManufacturingOrder.status == OrderStatus.RELEASED
            ).all()
            assembly_queue_count = len(released_orders)
            for order in released_orders:
                if order.product and order.product.assembly_hours:
                    assembly_queue_hours += float(order.product.assembly_hours) * order.quantity
        except Exception:
            pass

        # Get daily assembly capacity and cost info
        daily_assembly_hours = 0.0
        cost_per_worker_per_hour = 0.0
        cost_per_assembly_line = 0.0
        max_workers_per_line = 10
        try:
            if sim_config:
                wpl = sim_config.workers_per_line or 1
                lines = sim_config.assembly_lines or 1
                sh = float(sim_config.shift_hours or 8)
                daily_assembly_hours = float(lines * wpl * sh)
                cost_per_worker_per_hour = float(sim_config.cost_per_worker_per_hour or 50)
                cost_per_assembly_line = float(sim_config.cost_per_assembly_line or 50000)
                max_workers_per_line = int(sim_config.max_workers_per_line or 10)
        except Exception:
            pass

        # Get inbound purchase orders (arriving today or later, with their delivery status)
        arriving_today = []
        arriving_future = []
        rejected_today = []
        try:
            from datetime import date as date_type
            sim_date_obj = sim_date if isinstance(sim_date, date_type) else sim_date

            # All orders with expected_delivery >= today (pending, delivered, or rejected)
            inbound_rows = session.query(PurchaseOrder).filter(
                PurchaseOrder.expected_delivery >= sim_date_obj
            ).all()

            for purchase in inbound_rows:
                if purchase.supplier and purchase.supplier.product:
                    # Calculate expected arrival day relative to simulation date
                    days_until_delivery = (purchase.expected_delivery - sim_date_obj).days

                    order_info = {
                        "id": purchase.id,
                        "product": purchase.supplier.product.name,
                        "quantity": float(purchase.quantity or 0),
                        "supplier": purchase.supplier.name,
                        "expected_delivery_date": str(purchase.expected_delivery),
                        "days_until": days_until_delivery,
                    }

                    # Categorize by delivery date and status
                    if days_until_delivery == 0:
                        # Arriving today
                        if purchase.status == PurchaseOrderStatus.REJECTED:
                            rejected_today.append({
                                **order_info,
                                "status": "REJECTED",
                                "reason": "Warehouse capacity exceeded on delivery",
                            })
                        elif purchase.status == PurchaseOrderStatus.DELIVERED:
                            arriving_today.append({
                                **order_info,
                                "status": "RECEIVED TODAY",
                            })
                        else:  # PENDING
                            arriving_today.append({
                                **order_info,
                                "status": "PENDING (arriving today)",
                            })
                    else:
                        # Arriving in future (only show PENDING, since future deliveries haven't happened yet)
                        if purchase.status == PurchaseOrderStatus.PENDING:
                            arriving_future.append({
                                **order_info,
                                "status": "PENDING",
                            })
        except Exception:
            pass

        backlog_days = (assembly_queue_hours / daily_assembly_hours) if daily_assembly_hours > 0 else 0.0

        return {
            "day": {"date": str(sim_date)},
            "inventory": inventory_dict,
            "assembly_queue": {
                "released_count": assembly_queue_count,
                "queued_hours": round(assembly_queue_hours, 1),
                "daily_capacity_hours": round(daily_assembly_hours, 1),
                "backlog_days": round(backlog_days, 2),
                "cost_per_worker_per_hour": cost_per_worker_per_hour,
                "cost_per_assembly_line": cost_per_assembly_line,
                "max_workers_per_line": max_workers_per_line,
            },
            "sales_orders": {
                "pending_count": len(pending_orders),
                "pending": pending_orders[:20],  # Limit to first 20
            },
            "purchase_orders": {
                "arriving_today": arriving_today,
                "arriving_future": arriving_future,
                "rejected_today": rejected_today,
                "total_inbound": len(arriving_today) + len(arriving_future),
            },
            "products": product_dict,
        }
    except Exception as e:
        return {"error": str(e), "message": "State snapshot incomplete"}
