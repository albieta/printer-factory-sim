"""KPI collection and CSV logging for the turn engine."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_COLUMNS = [
    "day",
    "demand_modifier",
    "retailer_stock_total",
    "retailer_pending_pos",
    "retailer_backordered_customers",
    "manufacturer_pending_sales",
    "manufacturer_inventory_total",
    "provider_stock_total",
]


def collect_kpis(
    day: int,
    signal: dict[str, Any],
    retailer_url: str,
    manufacturer_url: str,
    provider_url: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "day": day,
        "demand_modifier": signal.get("demand_modifier", 1.0),
        "retailer_stock_total": _retailer_stock(retailer_url),
        "retailer_pending_pos": _retailer_pending_pos(retailer_url),
        "retailer_backordered_customers": _retailer_backordered(retailer_url),
        "manufacturer_pending_sales": _manufacturer_pending_sales(manufacturer_url),
        "manufacturer_inventory_total": _manufacturer_inventory(manufacturer_url),
        "provider_stock_total": _provider_stock(provider_url),
    }
    return row


def append_kpi_row(log_dir: Path, row: dict[str, Any]) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "kpi.csv"
    write_header = not path.exists()
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# ── private helpers ────────────────────────────────────────────────────────────

def _get(url: str) -> list[dict[str, Any]]:
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data
    except httpx.HTTPError as exc:
        logger.warning("KPI fetch failed %s: %s", url, exc)
        return []


def _retailer_stock(base: str) -> float:
    items = _get(f"{base.rstrip('/')}/api/stock")
    return sum(float(i.get("quantity", 0)) for i in items)


def _retailer_pending_pos(base: str) -> int:
    pos = _get(f"{base.rstrip('/')}/api/purchases")
    return sum(1 for po in pos if po.get("status") in ("PENDING", "pending"))


def _retailer_backordered(base: str) -> int:
    orders = _get(f"{base.rstrip('/')}/api/orders")
    return sum(
        1 for o in orders if o.get("status") in ("BACKORDERED", "backordered")
    )


def _manufacturer_pending_sales(base: str) -> int:
    orders = _get(f"{base.rstrip('/')}/api/sales/orders")
    return sum(1 for o in orders if o.get("status") == "PENDING")


def _manufacturer_inventory(base: str) -> float:
    try:
        resp = httpx.get(f"{base.rstrip('/')}/api/inventory/", timeout=5.0, follow_redirects=True)
        resp.raise_for_status()
        items: list[dict[str, Any]] = resp.json()
        return sum(float(i.get("quantity", 0)) for i in items)
    except httpx.HTTPError as exc:
        logger.warning("KPI manufacturer inventory failed: %s", exc)
        return 0.0


def _provider_stock(base: str) -> float:
    items = _get(f"{base.rstrip('/')}/api/stock")
    return sum(float(i.get("quantity", 0)) for i in items)
