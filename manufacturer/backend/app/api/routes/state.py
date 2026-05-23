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
            SimulationConfig, Inventory, SalesOrder, PurchaseOrder, Product, WholesalePrice
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

        # Get inbound purchase orders
        inbound_list = []
        try:
            inbound_rows = session.query(PurchaseOrder).filter(
                PurchaseOrder.status.in_(["PENDING", "CONFIRMED", "IN_PROGRESS"])
            ).all()
            for purchase in inbound_rows:
                if purchase.supplier and purchase.supplier.product:
                    inbound_list.append({
                        "id": purchase.id,
                        "product": purchase.supplier.product.name,
                        "quantity": float(purchase.quantity or 0),
                        "supplier": purchase.supplier.name,
                        "status": purchase.status,
                        "expected_arrival_day": purchase.expected_arrival_day or 999,
                    })
        except Exception:
            pass

        return {
            "day": {"date": str(sim_date)},
            "inventory": inventory_dict,
            "sales_orders": {
                "pending_count": len(pending_orders),
                "pending": pending_orders[:20],  # Limit to first 20
            },
            "purchase_orders": {
                "inbound_count": len(inbound_list),
                "inbound": inbound_list,
            },
            "products": product_dict,
        }
    except Exception as e:
        return {"error": str(e), "message": "State snapshot incomplete"}
