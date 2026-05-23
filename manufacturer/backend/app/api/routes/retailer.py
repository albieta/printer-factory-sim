"""REST endpoints for proxying retailer data."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter

router = APIRouter()

RETAILER_URL = os.environ.get("RETAILER_BASE_URL", "http://localhost:8003")
TIMEOUT = 5.0


def _retailer_request(endpoint: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Make HTTP request to retailer API. Returns None if offline."""
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{RETAILER_URL}{endpoint}")
            if response.status_code == 200:
                return response.json()
    except (httpx.RequestError, httpx.TimeoutException):
        pass
    return None


@router.get("/status")
def retailer_status() -> dict[str, Any]:
    """Check retailer health and current day."""
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{RETAILER_URL}/health")
            if response.status_code == 200:
                return {"available": True, "status": "online"}
    except (httpx.RequestError, httpx.TimeoutException):
        pass
    return {"available": False, "status": "offline"}


@router.get("/stock")
def retailer_stock() -> dict[str, Any]:
    """Get retailer's current stock levels."""
    result = _retailer_request("/api/stock")
    if result is None:
        return {"schema_version": 1, "items": [], "available": False}
    if isinstance(result, dict):
        result["available"] = True
        return result
    return {"schema_version": 1, "items": result, "available": True}


@router.get("/orders")
def retailer_orders(status: str | None = None) -> dict[str, Any]:
    """Get retailer's customer orders."""
    endpoint = "/api/orders"
    if status:
        endpoint += f"?status={status}"
    result = _retailer_request(endpoint)
    if result is None:
        return {"orders": [], "available": False}
    if isinstance(result, list):
        return {"orders": result, "available": True}
    return result


@router.get("/purchases")
def retailer_purchases() -> dict[str, Any]:
    """Get retailer's purchase orders to manufacturer."""
    result = _retailer_request("/api/purchases")
    if result is None:
        return {"purchases": [], "available": False}
    if isinstance(result, list):
        return {"purchases": result, "available": True}
    return result


@router.get("/summary")
def retailer_summary() -> dict[str, Any]:
    """Get aggregated retailer financial and operational summary."""
    # Fetch orders to compute summary
    orders_result = _retailer_request("/api/orders")
    if orders_result is None or not isinstance(orders_result, list):
        return {
            "available": False,
            "current_day": 0,
            "fulfilled_count": 0,
            "backordered_count": 0,
            "total_revenue": 0.0,
        }

    # Fetch day info
    day_result = _retailer_request("/api/day/current")
    current_day = 0
    if day_result and isinstance(day_result, dict):
        current_day = day_result.get("current_day", 0)

    # Compute summary from orders
    fulfilled_count = 0
    backordered_count = 0
    total_revenue = 0.0

    for order in orders_result:
        if isinstance(order, dict):
            status = order.get("status", "")
            if status == "FULFILLED":
                fulfilled_count += 1
                total_revenue += float(order.get("total_price", 0))
            elif status == "BACKORDERED":
                backordered_count += 1

    return {
        "available": True,
        "current_day": current_day,
        "fulfilled_count": fulfilled_count,
        "backordered_count": backordered_count,
        "total_revenue": round(total_revenue, 2),
    }
