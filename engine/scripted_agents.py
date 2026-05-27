"""Deterministic scripted agents — fast_mode replacement for claude --print.

Each function replicates the corresponding skill file's Decision Framework
using direct HTTP calls (state) and CLI subprocess calls (actions).
No LLM tokens consumed. Per-day wall time: <5 seconds for all three roles.

Parallelism note: these functions are thread-safe; the turn engine runs them
concurrently via ThreadPoolExecutor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

LOGS_DIR = Path("logs")
_DEFAULT_HTTP_TIMEOUT = 8.0

# ── Starting stock targets (mirrors skill file references) ────────────────────

_PROVIDER_STARTING_STOCK: dict[str, int] = {
    "Control Board": 500,
    "Stepper Motor": 800,
    "Aluminum Frame": 300,
    "PLA Filament": 1000,
    "ABS Filament": 800,
    "LCD Screen": 200,
}

_RETAILER_MIN_STOCK: dict[str, int] = {
    "Basic300": 5,
    "Pro450": 3,
    "Elite700": 1,
}

# ── HTTP helpers ──────────────────────────────────────────────────────────────


def _get(url: str) -> dict[str, Any]:
    with httpx.Client(timeout=_DEFAULT_HTTP_TIMEOUT) as c:
        r = c.get(url)
        r.raise_for_status()
        return dict(r.json())


def _get_list(url: str) -> list[Any]:
    with httpx.Client(timeout=_DEFAULT_HTTP_TIMEOUT) as c:
        r = c.get(url)
        r.raise_for_status()
        data = r.json()
        return list(data) if isinstance(data, list) else list(data.get("items", data.get("orders", [])))


def _post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=_DEFAULT_HTTP_TIMEOUT) as c:
        r = c.post(url, json=body)
        r.raise_for_status()
        return dict(r.json())


def _patch(url: str, body: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=_DEFAULT_HTTP_TIMEOUT) as c:
        r = c.patch(url, json=body)
        r.raise_for_status()
        return dict(r.json())


def _put(url: str, body: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=_DEFAULT_HTTP_TIMEOUT) as c:
        r = c.put(url, json=body)
        r.raise_for_status()
        return dict(r.json())


def _write_log(day: int, role: str, content: str) -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    path = LOGS_DIR / f"day-{day:03d}-{role}.log"
    path.write_text(content, encoding="utf-8")


# ── Provider scripted agent ───────────────────────────────────────────────────


def run_scripted_provider(
    role: str,
    day: int,
    signal: dict[str, Any],
    cfg: dict[str, Any],
) -> str:
    """Scripted provider: restock low products, adjust top-tier prices."""

    url = cfg["url"]
    demand_mod: float = float(signal.get("demand_modifier", 1.0))
    supply_mod: float = float(signal.get("supply_modifier", 1.0))
    log_lines: list[str] = [f"=== [fast-mode] Provider scripted agent — Day {day} ===\n"]
    actions: list[str] = []

    # ── 1. Fetch state ────────────────────────────────────────────────────────
    try:
        stock_list = _get_list(f"{url}/api/stock")
        catalog_data = _get(f"{url}/api/catalog")
    except Exception as exc:
        msg = f"[scripted-provider] state fetch failed: {exc}"
        _write_log(day, role, msg)
        return msg

    stock_by_name: dict[str, int] = {}
    for item in stock_list:
        if isinstance(item, dict):
            stock_by_name[item.get("product_name", "")] = int(item.get("quantity", 0))

    # Build top-tier price map from catalog
    top_tier_by_name: dict[str, dict[str, Any]] = {}
    products_list = catalog_data.get("products", [])
    for prod in products_list:
        name = prod.get("name", "")
        tiers = prod.get("pricing_tiers", [])
        if tiers:
            top = max(tiers, key=lambda t: t.get("min_quantity", 0))
            top_tier_by_name[name] = top

    log_lines.append(f"Stock snapshot: {json.dumps(stock_by_name, indent=2)}\n")

    # ── 2. Restock ────────────────────────────────────────────────────────────
    restock_threshold = 0.75 if demand_mod > 1.5 else 0.50
    restocked: list[str] = []

    for product_name, starting in _PROVIDER_STARTING_STOCK.items():
        current = stock_by_name.get(product_name, 0)
        if current < restock_threshold * starting:
            qty_to_add = starting - current
            try:
                _post(f"{url}/api/stock/restock", {"product_name": product_name, "quantity": qty_to_add})
                restocked.append(f"{product_name} +{qty_to_add}")
                actions.append(f"Restocked {product_name} by {qty_to_add} (was {current}/{starting})")
            except Exception as exc:
                actions.append(f"Restock failed for {product_name}: {exc}")

    log_lines.append(f"Restocked: {', '.join(restocked) if restocked else 'none'}\n")

    # ── 3. Adjust prices ──────────────────────────────────────────────────────
    price_changes: list[str] = []
    for product_name, starting in _PROVIDER_STARTING_STOCK.items():
        current = stock_by_name.get(product_name, 0)
        top_tier = top_tier_by_name.get(product_name)
        if not top_tier:
            continue

        current_price = float(top_tier.get("unit_price", 0))
        min_qty = int(top_tier.get("min_quantity", 1))
        new_price: float | None = None

        if current < 0.30 * starting and supply_mod < 0.7:
            new_price = round(current_price * 1.10, 2)
        elif current < 0.30 * starting:
            new_price = round(current_price * 1.07, 2)
        elif current > 1.50 * starting and demand_mod <= 1.5:
            new_price = round(current_price * 0.93, 2)

        if new_price is not None:
            try:
                _patch(
                    f"{url}/api/catalog/{product_name}/price",
                    {"min_quantity": min_qty, "unit_price": str(new_price)},
                )
                price_changes.append(f"{product_name} tier {min_qty}: {current_price:.2f}→{new_price:.2f}")
            except Exception as exc:
                actions.append(f"Price change failed for {product_name}: {exc}")

    log_lines.append(f"Price changes: {', '.join(price_changes) if price_changes else 'none'}\n")

    # ── 4. Summary ────────────────────────────────────────────────────────────
    summary_lines = [
        f"- Day {day} complete.",
        f"- Restocked: {', '.join(restocked) if restocked else 'none'}",
        f"- Price changes: {', '.join(price_changes) if price_changes else 'none'}",
        f"- Signal: demand×{demand_mod} supply×{supply_mod}",
        "- Mode: fast/scripted",
    ]
    summary = "\n".join(summary_lines)
    log_lines.append("=== SUMMARY ===\n" + summary)
    _write_log(day, role, "\n".join(log_lines))
    return summary


# ── Retailer scripted agent ───────────────────────────────────────────────────


def run_scripted_retailer(
    role: str,
    day: int,
    signal: dict[str, Any],
    cfg: dict[str, Any],
) -> str:
    """Scripted retailer: replenish low-stock models, adjust prices."""

    url = cfg["url"]
    demand_mod: float = float(signal.get("demand_modifier", 1.0))
    price_sensitivity: str = str(signal.get("price_sensitivity", "normal"))
    log_lines: list[str] = [f"=== [fast-mode] Retailer scripted agent — Day {day} ===\n"]
    actions: list[str] = []

    # ── 1. Fetch state ────────────────────────────────────────────────────────
    try:
        stock_data = _get(f"{url}/api/stock")
        catalog_data = _get(f"{url}/api/catalog")
        purchases_data = _get_list(f"{url}/api/purchases")
    except Exception as exc:
        msg = f"[scripted-retailer] state fetch failed: {exc}"
        _write_log(day, role, msg)
        return msg

    stock_by_name: dict[str, int] = {}
    stock_list = stock_data if isinstance(stock_data, list) else stock_data.get("items", [])
    for item in stock_list:
        if isinstance(item, dict):
            stock_by_name[item.get("product_name", "")] = int(item.get("quantity", 0))

    price_by_name: dict[str, float] = {}
    entries = catalog_data.get("entries", [])
    for entry in entries:
        if isinstance(entry, dict):
            price_by_name[entry.get("product_name", "")] = float(entry.get("retail_price", 0))

    inbound_by_name: dict[str, int] = {}
    for po in purchases_data:
        if not isinstance(po, dict):
            continue
        if po.get("status") in ("PENDING", "CONFIRMED", "IN_PROGRESS", "pending", "confirmed", "in_progress"):
            name = po.get("product_name", "")
            inbound_by_name[name] = inbound_by_name.get(name, 0) + int(po.get("quantity", 0))

    log_lines.append(f"Stock: {json.dumps(stock_by_name)}, inbound: {json.dumps(inbound_by_name)}\n")

    # ── 2. Replenishment orders ───────────────────────────────────────────────
    purchases_placed: list[str] = []
    for model, min_stock in _RETAILER_MIN_STOCK.items():
        on_hand = stock_by_name.get(model, 0)
        inbound = inbound_by_name.get(model, 0)
        available = on_hand + inbound

        if demand_mod > 1.5:
            target = min_stock * 3
        elif demand_mod < 0.8:
            target = min_stock
        else:
            target = min_stock * 2

        if available < target:
            qty = target - available
            try:
                _post(f"{url}/api/purchases", {"product_name": model, "quantity": qty})
                purchases_placed.append(f"{model} ×{qty}")
                actions.append(f"Purchase order: {model} ×{qty} (have {on_hand}+{inbound}, target {target})")
            except Exception as exc:
                actions.append(f"Purchase failed for {model}: {exc}")

    log_lines.append(f"Purchases placed: {', '.join(purchases_placed) if purchases_placed else 'none'}\n")

    # ── 3. Price adjustments ──────────────────────────────────────────────────
    price_changes: list[str] = []
    for model, min_stock in _RETAILER_MIN_STOCK.items():
        on_hand = stock_by_name.get(model, 0)
        current_price = price_by_name.get(model)
        if not current_price:
            continue

        new_price: float | None = None
        if on_hand < min_stock and price_sensitivity != "high":
            new_price = round(current_price * 1.05, 2)
        elif on_hand > min_stock * 5 and demand_mod < 0.8:
            new_price = round(current_price * 0.95, 2)

        if new_price is not None:
            try:
                _put(
                    f"{url}/api/catalog/{model}/price",
                    {"product_name": model, "retail_price": str(new_price)},
                )
                price_changes.append(f"{model}: {current_price:.2f}→{new_price:.2f}")
            except Exception as exc:
                actions.append(f"Price change failed for {model}: {exc}")

    log_lines.append(f"Price changes: {', '.join(price_changes) if price_changes else 'none'}\n")

    # ── 4. Summary ────────────────────────────────────────────────────────────
    summary_lines = [
        f"- Day {day} complete.",
        "- Customer actions: handled by app auto-fulfill.",
        f"- Purchases placed: {', '.join(purchases_placed) if purchases_placed else 'none'}",
        f"- Price changes: {', '.join(price_changes) if price_changes else 'none'}",
        "- Mode: fast/scripted",
    ]
    summary = "\n".join(summary_lines)
    log_lines.append("=== SUMMARY ===\n" + summary)
    _write_log(day, role, "\n".join(log_lines))
    return summary


# ── Manufacturer scripted agent ───────────────────────────────────────────────


def run_scripted_manufacturer(
    role: str,
    day: int,
    signal: dict[str, Any],
    cfg: dict[str, Any],
) -> str:
    """Scripted manufacturer: release pending orders, order low materials, adjust prices."""

    url = cfg["url"]
    demand_mod: float = float(signal.get("demand_modifier", 1.0))
    log_lines: list[str] = [f"=== [fast-mode] Manufacturer scripted agent — Day {day} ===\n"]

    # ── 1. Fetch state ────────────────────────────────────────────────────────
    try:
        state = _get(f"{url}/api/state/all")
    except Exception as exc:
        msg = f"[scripted-manufacturer] state fetch failed: {exc}"
        _write_log(day, role, msg)
        return msg

    if "error" in state:
        # fallback individual fetches
        try:
            capacity_data = _get(f"{url}/api/capacity")
            inventory_data = _get(f"{url}/api/inventory")
            sales_data = _get(f"{url}/api/sales/orders?status=PENDING")
            purchase_data = _get(f"{url}/api/orders/purchase/")
            prices_data = _get(f"{url}/api/prices")
            state = {
                "capacity": capacity_data,
                "inventory": {item["name"]: item["quantity"] for item in inventory_data.get("items", [])},
                "sales_orders": {"pending": sales_data if isinstance(sales_data, list) else sales_data.get("orders", []), "pending_count": 0},
                "purchase_orders": {"inbound": purchase_data if isinstance(purchase_data, list) else []},
                "products": {k: {"price": v} for k, v in prices_data.get("prices", {}).items()},
            }
        except Exception as exc2:
            msg = f"[scripted-manufacturer] fallback state fetch failed: {exc2}"
            _write_log(day, role, msg)
            return msg

    capacity = state.get("capacity", {})
    daily_hours = float(capacity.get("daily_hours", capacity.get("daily_assembly_hours", 8.0)))
    inventory: dict[str, float] = {k: float(v) for k, v in state.get("inventory", {}).items()}
    pending_orders: list[dict[str, Any]] = state.get("sales_orders", {}).get("pending", [])
    inbound_pos: list[dict[str, Any]] = state.get("purchase_orders", {}).get("inbound", [])
    prices: dict[str, Any] = state.get("products", {})

    log_lines.append(
        f"Capacity: {daily_hours}h/day | Inventory: {json.dumps(inventory)} | "
        f"Pending orders: {len(pending_orders)}\n"
    )

    # ── 2. Release pending sales orders ──────────────────────────────────────
    hours_used = 0.0
    released: list[str] = []
    for order in pending_orders:
        if hours_used >= daily_hours:
            break
        order_id = order.get("id", "")
        if not order_id:
            continue
        try:
            _post(f"{url}/api/production/release", {"order_id": str(order_id)})
            hours_used += 1.0
            released.append(str(order_id))
        except Exception as exc:
            log_lines.append(f"Release failed for {order_id}: {exc}\n")

    log_lines.append(f"Released: {len(released)} order(s): {', '.join(released[:5])}\n")

    # ── 3. Order low materials ────────────────────────────────────────────────
    inbound_by_product: dict[str, float] = {}
    for po in inbound_pos:
        name = po.get("product", "")
        inbound_by_product[name] = inbound_by_product.get(name, 0) + float(po.get("quantity", 0))

    purchases_placed: list[str] = []
    low_threshold = 50.0
    replenish_qty = 200

    for material, qty in inventory.items():
        already_inbound = inbound_by_product.get(material, 0)
        if qty < low_threshold and already_inbound < low_threshold:
            # Use HTTP API to create purchase order (consistent with provider/retailer agents)
            # The service finds the appropriate supplier for the material
            try:
                _post(
                    f"{url}/api/purchase-orders/",
                    {
                        "supplier_id": "ChipSupply Co",  # Default supplier; in practice would query first
                        "product_id": material,
                        "quantity": int(replenish_qty),
                    }
                )
                purchases_placed.append(f"{material} ×{replenish_qty}")
            except Exception as exc:
                log_lines.append(f"Purchase order creation failed for {material}: {exc}\n")

    log_lines.append(f"Purchases placed: {', '.join(purchases_placed) if purchases_placed else 'none'}\n")

    # ── 4. Price adjustments ──────────────────────────────────────────────────
    price_changes: list[str] = []
    for model, prod_info in prices.items():
        current_price = float(prod_info.get("price", 0)) if isinstance(prod_info, dict) else float(prod_info)
        if current_price <= 0:
            continue
        new_price: float | None = None
        if demand_mod > 1.5:
            new_price = round(current_price * 1.10, 2)
        elif demand_mod < 0.5:
            new_price = round(current_price * 0.95, 2)

        if new_price is not None:
            try:
                _post(f"{url}/api/prices", {"model": model, "price": str(new_price)})
                price_changes.append(f"{model}: {current_price:.2f}→{new_price:.2f}")
            except Exception as exc:
                log_lines.append(f"Price set failed for {model}: {exc}\n")

    log_lines.append(f"Price changes: {', '.join(price_changes) if price_changes else 'none'}\n")

    # ── 5. Summary ────────────────────────────────────────────────────────────
    summary_lines = [
        f"- Day {day} complete.",
        f"- Released {len(released)} sales order(s).",
        f"- Placed {len(purchases_placed)} purchase order(s).",
        f"- Capacity: {daily_hours}h/day.",
        f"- Price changes: {', '.join(price_changes) if price_changes else 'none'}.",
        "- Mode: fast/scripted",
    ]
    summary = "\n".join(summary_lines)
    log_lines.append("=== SUMMARY ===\n" + summary)
    _write_log(day, role, "\n".join(log_lines))
    return summary
