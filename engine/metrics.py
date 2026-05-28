"""Daily metric snapshots for Week 8 scenario analysis.

The turn engine writes one JSON line per simulated day to
``logs/metrics.jsonl``. The snapshot is intentionally API-derived, not
database-derived, so it preserves the three-service boundary.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from engine.api_logger import ApiLogger


DEFAULT_TIMEOUT = 10.0
METRICS_PATH = Path("logs") / "metrics.jsonl"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(row.get("status", "UNKNOWN")) for row in rows))


def _safe_get(url: str, logger: ApiLogger | None = None) -> Any:
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            response = client.get(url)
            try:
                body: Any = response.json()
            except ValueError:
                body = {"raw": response.text[:500]}
            if logger:
                logger.log("GET", url, None, response.status_code, body)
            response.raise_for_status()
            return body
    except httpx.HTTPError as exc:
        return {"error": str(exc)}


def _provider_snapshot(provider_cfg: dict[str, Any], logger: ApiLogger | None) -> dict[str, Any]:
    base_url = str(provider_cfg["url"]).rstrip("/")
    stock_data = _safe_get(f"{base_url}/api/stock", logger)
    catalog_data = _safe_get(f"{base_url}/api/catalog", logger)
    orders_data = _safe_get(f"{base_url}/api/orders", logger)

    stock: dict[str, int] = {}
    if isinstance(stock_data, list):
        stock = {
            str(row.get("product_name", row.get("product_id", "unknown"))): _to_int(row.get("quantity"))
            for row in stock_data
            if isinstance(row, dict)
        }

    prices: dict[str, dict[str, float]] = {}
    products = catalog_data.get("products", []) if isinstance(catalog_data, dict) else []
    for product in products:
        if not isinstance(product, dict):
            continue
        product_name = str(product.get("name", "unknown"))
        tiers = product.get("pricing_tiers", [])
        prices[product_name] = {
            str(tier.get("min_quantity")): _to_float(tier.get("unit_price"))
            for tier in tiers
            if isinstance(tier, dict)
        }

    orders = orders_data if isinstance(orders_data, list) else []
    return {
        "name": provider_cfg.get("name", "provider"),
        "stock": stock,
        "prices": prices,
        "orders": _status_counts([row for row in orders if isinstance(row, dict)]),
        "errors": [value["error"] for value in (stock_data, catalog_data, orders_data) if isinstance(value, dict) and "error" in value],
    }


def _manufacturer_snapshot(mfr_cfg: dict[str, Any], day: int, logger: ApiLogger | None) -> dict[str, Any]:
    base_url = str(mfr_cfg["url"]).rstrip("/")
    inventory_data = _safe_get(f"{base_url}/api/inventory/", logger)
    prices_data = _safe_get(f"{base_url}/api/prices", logger)
    sales_data = _safe_get(f"{base_url}/api/sales/orders", logger)
    production_data = _safe_get(f"{base_url}/api/production/status", logger)
    capacity_data = _safe_get(f"{base_url}/api/capacity", logger)
    financial_data = _safe_get(f"{base_url}/api/financial/summary", logger)
    transactions_data = _safe_get(f"{base_url}/api/financial/transactions?day={day}", logger)
    orders_daily_data = _safe_get(f"{base_url}/api/simulation/orders-daily?day={day}", logger)
    simulation_status_data = _safe_get(f"{base_url}/api/simulation/status", logger)

    inventory: dict[str, float] = {}
    if isinstance(inventory_data, list):
        inventory = {
            str(row.get("product_name", row.get("product_id", "unknown"))): _to_float(row.get("quantity"))
            for row in inventory_data
            if isinstance(row, dict)
        }

    prices: dict[str, float] = {}
    if isinstance(prices_data, dict):
        prices = {
            str(model): _to_float(price)
            for model, price in prices_data.get("prices", {}).items()
        }

    # Sales orders: placed_day uses prev_day (placed before advance); in_progress/shipped use day (set during advance).
    sales_orders = [row for row in sales_data if isinstance(row, dict)] if isinstance(sales_data, list) else []
    prev_day = max(0, day - 1)

    # Combined new/accepted/deleted from both MFG orders and SalesOrders.
    od = orders_daily_data if isinstance(orders_daily_data, dict) else {}
    mfg_created = _to_int(od.get("mfg_created"))
    so_placed = sum(1 for o in sales_orders if _to_int(o.get("placed_day"), -1) == prev_day)
    mfg_released = _to_int(od.get("mfg_released"))
    so_confirmed = _to_int(od.get("so_confirmed"))
    mfg_blocked = _to_int(od.get("mfg_blocked"))
    so_rejected = _to_int(od.get("so_rejected"))
    so_shipped = sum(1 for o in sales_orders if _to_int(o.get("shipped_day"), -1) == day)

    sales_orders_today = {
        "placed": mfg_created + so_placed,
        "in_progress": mfg_released + so_confirmed,
        "shipped": so_shipped,
        "rejected": mfg_blocked + so_rejected,
    }

    active_count = 0
    if isinstance(production_data, dict):
        active_count = _to_int(production_data.get("count"))

    financials: dict[str, float] = {}
    if isinstance(financial_data, dict):
        financials = {
            "total_costs": _to_float(financial_data.get("total_costs")),
            "total_revenue": _to_float(financial_data.get("total_revenue")),
            "net_profit": _to_float(financial_data.get("net_profit")),
        }

    daily_financials: dict[str, float] = {"revenue": 0.0, "costs": 0.0, "net_profit": 0.0}
    if isinstance(transactions_data, list):
        rev = sum(_to_float(t.get("amount")) for t in transactions_data if isinstance(t, dict) and t.get("type") == "PRODUCT_SOLD")
        # Costs are stored as negative values in the database; take absolute value for reporting
        cost = abs(sum(_to_float(t.get("amount")) for t in transactions_data if isinstance(t, dict) and t.get("type") != "PRODUCT_SOLD"))
        daily_financials = {"revenue": rev, "costs": cost, "net_profit": rev - cost}

    # Extract queued assembly hours and queue load percentage from simulation status
    queued_assembly_hours: float | None = None
    queue_load_percentage: float | None = None
    if isinstance(simulation_status_data, dict):
        queued_assembly_hours = _to_float(simulation_status_data.get("queued_assembly_hours"))
        queue_load_percentage = _to_float(simulation_status_data.get("queue_load_percentage"))

    all_data = (inventory_data, prices_data, sales_data, production_data, capacity_data, financial_data, transactions_data, orders_daily_data, simulation_status_data)
    result = {
        "name": mfr_cfg.get("name", "manufacturer"),
        "inventory": inventory,
        "prices": prices,
        "sales_orders": _status_counts(sales_orders),
        "active_production_orders": active_count,
        "capacity": capacity_data if isinstance(capacity_data, dict) else {},
        "financials": financials,
        "sales_orders_today": sales_orders_today,
        "daily_financials": daily_financials,
        "errors": [
            value["error"]
            for value in all_data
            if isinstance(value, dict) and "error" in value
        ],
    }
    # Add queued assembly hours and queue load percentage if available
    if queued_assembly_hours is not None:
        result["queued_assembly_hours"] = queued_assembly_hours
    if queue_load_percentage is not None:
        result["queue_load_percentage"] = queue_load_percentage
    return result


def _retailer_snapshot(
    retailer_cfg: dict[str, Any],
    day: int,
    logger: ApiLogger | None,
) -> dict[str, Any]:
    base_url = str(retailer_cfg["url"]).rstrip("/")
    stock_data = _safe_get(f"{base_url}/api/stock", logger)
    catalog_data = _safe_get(f"{base_url}/api/catalog", logger)
    orders_data = _safe_get(f"{base_url}/api/orders", logger)
    purchases_data = _safe_get(f"{base_url}/api/purchases", logger)

    stock: dict[str, int] = {}
    if isinstance(stock_data, dict):
        stock = {
            str(row.get("product_name", "unknown")): _to_int(row.get("quantity"))
            for row in stock_data.get("items", [])
            if isinstance(row, dict)
        }

    prices: dict[str, float] = {}
    if isinstance(catalog_data, dict):
        prices = {
            str(row.get("product_name", "unknown")): _to_float(row.get("retail_price"))
            for row in catalog_data.get("entries", [])
            if isinstance(row, dict)
        }

    customer_orders = [row for row in orders_data if isinstance(row, dict)] if isinstance(orders_data, list) else []
    # Orders are injected before advance_app, so the retailer's sim_day at placement
    # time is always (engine_day - 1).  Snapshot runs after the advance.
    order_day = day - 1
    today_orders = [row for row in customer_orders if _to_int(row.get("placed_day"), -1) == order_day]
    today_counts = _status_counts(today_orders)
    # Orders placed on engine_day can be fulfilled either before or after the retailer's advance:
    # - Fulfilled before advance: fulfilled_day = day - 1
    # - Fulfilled after advance: fulfilled_day = day
    # Include both to capture orders fulfilled same day (placed before advance, fulfilled after)
    fulfilled_today = sum(1 for row in customer_orders if _to_int(row.get("fulfilled_day"), -1) in [day - 1, day] and _to_int(row.get("placed_day"), -1) == order_day)
    purchase_orders = [row for row in purchases_data if isinstance(row, dict)] if isinstance(purchases_data, list) else []

    return {
        "name": retailer_cfg.get("name", "retailer"),
        "stock": stock,
        "prices": prices,
        "customer_orders": {
            "status_counts": _status_counts(customer_orders),
            "placed_today": len(today_orders),
            "fulfilled_today": fulfilled_today,
            "backordered_today": today_counts.get("BACKORDERED", 0),
            "cancelled_today": today_counts.get("CANCELLED", 0),
        },
        "purchases": _status_counts(purchase_orders),
        "errors": [
            value["error"]
            for value in (stock_data, catalog_data, orders_data, purchases_data)
            if isinstance(value, dict) and "error" in value
        ],
    }


def snapshot_metrics(
    config: dict[str, Any],
    scenario: dict[str, Any],
    day: int,
    signal: dict[str, Any],
    logger: ApiLogger | None = None,
) -> dict[str, Any]:
    """Capture one post-advance snapshot from all configured apps."""

    retailers = [
        _retailer_snapshot(retailer_cfg, day, logger)
        for retailer_cfg in config.get("retailers", [])
    ]
    providers = [
        _provider_snapshot(provider_cfg, logger)
        for provider_cfg in config.get("providers", [])
    ]

    return {
        "ts": datetime.utcnow().isoformat(),
        "scenario": scenario.get("scenario_name", "unnamed"),
        "day": day,
        "signal": signal,
        "retailers": retailers,
        "manufacturer": _manufacturer_snapshot(config.get("manufacturer", {}), day, logger),
        "providers": providers,
    }


def append_metrics(snapshot: dict[str, Any], path: Path = METRICS_PATH) -> None:
    """Append a snapshot as one JSON line."""

    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, default=str) + "\n")


def summarize_metrics(snapshot: dict[str, Any]) -> str:
    """Return the Week 8 one-line daily summary."""

    placed = 0
    fulfilled = 0
    backordered = 0
    for retailer in snapshot.get("retailers", []):
        if not isinstance(retailer, dict):
            continue
        orders = retailer.get("customer_orders", {})
        if not isinstance(orders, dict):
            continue
        placed += _to_int(orders.get("placed_today"))
        fulfilled += _to_int(orders.get("fulfilled_today"))
        backordered += _to_int(orders.get("backordered_today"))

    active_events = snapshot.get("signal", {}).get("active_events", [])
    if isinstance(active_events, list) and active_events:
        event_text = ",".join(str(event) for event in active_events)
    else:
        event_text = "none"

    return (
        f"Day {snapshot.get('day')}: {placed} customer orders / "
        f"{fulfilled} fulfilled / {backordered} backordered; events={event_text}"
    )
