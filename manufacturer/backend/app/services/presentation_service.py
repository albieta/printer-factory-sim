from __future__ import annotations

from typing import Any

from app.models.models import OrderStatus
from app.services.starter_profile import ORDER_STATUS_LABELS, PURCHASE_ORDER_STATUS_LABELS


def get_order_status_label(status: Any) -> str:
    key = getattr(status, "value", status)
    return ORDER_STATUS_LABELS.get(key, str(key))



def get_purchase_order_status_label(status: Any) -> str:
    key = getattr(status, "value", status)
    return PURCHASE_ORDER_STATUS_LABELS.get(key, str(key))



def serialize_manufacturing_order(order: Any) -> dict[str, Any]:
    status_label = get_order_status_label(order.status)
    if getattr(order, "status", None) == OrderStatus.BLOCKED:
        status_label = (
            "Queued for Production but Blocked by Material Shortage"
            if getattr(order, "released_date", None)
            else "Awaiting Release but Blocked by Material Shortage"
        )

    return {
        "id": order.id,
        "reference_code": order.reference_code,
        "product_id": order.product_id,
        "product_name": order.product.name if getattr(order, "product", None) else None,
        "quantity": order.quantity,
        "status": order.status,
        "status_label": status_label,
        "status_reason": order.status_reason,
        "created_date": order.created_date,
        "released_date": order.released_date,
        "completed_date": order.completed_date,
    }



def serialize_purchase_order(order: Any) -> dict[str, Any]:
    total_cost = float(order.quantity * order.unit_cost)
    return {
        "id": order.id,
        "reference_code": order.reference_code,
        "supplier_id": order.supplier_id,
        "supplier_name": order.supplier.name if getattr(order, "supplier", None) else None,
        "product_id": order.product_id,
        "product_name": order.product.name if getattr(order, "product", None) else None,
        "quantity": order.quantity,
        "issue_date": order.issue_date,
        "expected_delivery": order.expected_delivery,
        "actual_delivery": order.actual_delivery,
        "status": order.status,
        "status_label": get_purchase_order_status_label(order.status),
        "status_reason": order.status_reason,
        "unit_cost": float(order.unit_cost),
        "total_cost": total_cost,
        "external_order_id": getattr(order, "external_order_id", None),
    }
