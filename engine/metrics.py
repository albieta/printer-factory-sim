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


def _manufacturer_snapshot(mfr_cfg: dict[str, Any], logger: ApiLogger | None) -> dict[str, Any]:
    base_url = str(mfr_cfg["url"]).rstrip("/")
    inventory_data = _safe_get(f"{base_url}/api/inventory/", logger)
    prices_data = _safe_get(f"{base_url}/api/prices", logger)
    sales_data = _safe_get(f"{base_url}/api/sales/orders", logger)
    production_data = _safe_get(f"{base_url}/api/production/status", logger)
    capacity_data = _safe_get(f"{base_url}/api/capacity", logger)
    financial_data = _safe_get(f"{base_url}/api/financial/summary", logger)

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

    sales_orders = sales_data if isinstance(sales_data, list) else []
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

    return {
        "name": mfr_cfg.get("name", "manufacturer"),
        "inventory": inventory,
        "prices": prices,
        "sales_orders": _status_counts([row for row in sales_orders if isinstance(row, dict)]),
        "active_production_orders": active_count,
        "capacity": capacity_data if isinstance(capacity_data, dict) else {},
        "financials": financials,
        "errors": [
            value["error"]
            for value in (inventory_data, prices_data, sales_data, production_data, capacity_data, financial_data)
            if isinstance(value, dict) and "error" in value
        ],
    }


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
    purchase_orders = [row for row in purchases_data if isinstance(row, dict)] if isinstance(purchases_data, list) else []

    return {
        "name": retailer_cfg.get("name", "retailer"),
        "stock": stock,
        "prices": prices,
        "customer_orders": {
            "status_counts": _status_counts(customer_orders),
            "placed_today": len(today_orders),
            "fulfilled_today": today_counts.get("FULFILLED", 0),
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
        "manufacturer": _manufacturer_snapshot(config.get("manufacturer", {}), logger),
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
