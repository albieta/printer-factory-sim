"""Turn engine — orchestrates one simulated day across all three apps.

Usage::

    python -m engine.turn_engine config/sim.json scenarios/smoke-test.json <num_days>

Each turn:
1. Inject customer demand at each retailer (POST /api/orders to retailer).
2. Run each role's decision hook (stub or ``claude --print``).
3. Advance the retailer (POST /api/day/advance).
4. Advance the manufacturer (POST /api/day/advance).
5. Advance each provider (POST /api/day/advance).

Day-advance order: retailer → manufacturer → provider (downstream first,
per PRD-week7 §3.1 and §9).

The engine never reads a database directly — all state access goes through
each app's REST surface.

Agent execution order: retailer → manufacturer → provider (sequential).
State is pre-fetched concurrently before agents start, then re-fetched
for the manufacturer after retailer agents complete so it sees orders
placed by the retailer during its turn.

Fast mode (FAST_MODE=true env var): scripted deterministic agents run instead
of claude subprocesses — no LLM tokens, ~60× faster per day.

The manufacturer's internal demand generator (Settings → "Internal demand
generator") is controlled entirely by the operator. The engine reads it at
startup and warns if it is on, but never overrides it.
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from engine.api_logger import ApiLogger
from engine.demand import generate_customer_demand, get_day_signal
from engine.agent_runner import build_prompt, run_agent
from engine.metrics import append_metrics, snapshot_metrics, summarize_metrics


DEFAULT_TIMEOUT = 10.0    # seconds for routine API calls
ADVANCE_TIMEOUT = 180.0   # day advance may trigger downstream HTTP polls; doubled for safety


# ── helpers ──────────────────────────────────────────────────────────────────


def _post(url: str, payload: dict[str, Any], logger: ApiLogger | None = None) -> Any:
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        r = client.post(url, json=payload)
        try:
            data = r.json() if r.content else {}
        except Exception:
            data = {}
        if logger:
            logger.log("POST", url, payload, r.status_code, data)
        r.raise_for_status()
    return data


def _get(url: str, logger: ApiLogger | None = None) -> Any:
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        r = client.get(url)
        try:
            data = r.json() if r.content else {}
        except Exception:
            data = {}
        if logger:
            logger.log("GET", url, None, r.status_code, data)
        r.raise_for_status()
    return data


def _put(url: str, payload: dict[str, Any], logger: ApiLogger | None = None) -> Any:
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        r = client.put(url, json=payload)
        try:
            data = r.json() if r.content else {}
        except Exception:
            data = {}
        if logger:
            logger.log("PUT", url, payload, r.status_code, data)
        r.raise_for_status()
    return data


_MANUFACTURER_DEFAULTS: dict[str, float] = {
    "assembly_lines": 1.0,
    "workers_per_line": 1.0,
    "shift_hours": 8.0,
    "cost_per_assembly_line": 50000.0,
    "cost_per_worker_per_hour": 50.0,
    "max_workers_per_line": 10.0,
}


def apply_scenario_config(mfr_url: str, scenario: dict[str, Any]) -> Any:
    """Apply scenario recommended_assembly / recommended_costs to the manufacturer.

    Only overrides fields that are still at their default values so that
    operator customisations made before the run (e.g. via the UI's
    "Apply recommended" button) are preserved.

    Returns the resulting config dict (or an empty dict on network error).
    """
    try:
        current = _get(f"{mfr_url}/api/config/")
    except httpx.HTTPError:
        return {}

    candidates: dict[str, Any] = {
        **scenario.get("recommended_assembly", {}),
        **scenario.get("recommended_costs", {}),
    }

    updates: dict[str, Any] = {}
    for key, recommended_val in candidates.items():
        default = _MANUFACTURER_DEFAULTS.get(key)
        current_val = current.get(key) if isinstance(current, dict) else None
        if default is not None and current_val is not None:
            if abs(float(current_val) - float(default)) < 0.01:
                updates[key] = recommended_val

    if not updates:
        return current

    try:
        return _put(f"{mfr_url}/api/config/", updates)
    except httpx.HTTPError:
        return current


def _retailer_base_prices(retailer_url: str, logger: ApiLogger | None = None) -> dict[str, float]:
    """Fetch the retailer's current catalog prices (used as demand baseline)."""
    data = _get(f"{retailer_url}/api/catalog", logger=logger)
    catalog = data.get("entries", data.get("catalog", []))
    prices: dict[str, float] = {}
    for entry in catalog:
        if not isinstance(entry, dict):
            continue
        try:
            prices[str(entry["product_name"])] = float(entry["retail_price"])
        except (KeyError, TypeError, ValueError):
            continue
    return prices


def _fetch_retailer_state(retailer_url: str, logger: ApiLogger | None = None) -> dict[str, Any]:
    """Fetch all retailer state in parallel sub-requests."""
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as c:
            stock_r = c.get(f"{retailer_url}/api/stock")
            catalog_r = c.get(f"{retailer_url}/api/catalog")
            orders_r = c.get(f"{retailer_url}/api/orders")
            purchases_r = c.get(f"{retailer_url}/api/purchases")
            day_r = c.get(f"{retailer_url}/api/day/current")
        return {
            "stock": stock_r.json() if stock_r.is_success else [],
            "catalog": catalog_r.json() if catalog_r.is_success else {},
            "orders": orders_r.json() if orders_r.is_success else [],
            "purchases": purchases_r.json() if purchases_r.is_success else [],
            "day": day_r.json() if day_r.is_success else {},
        }
    except Exception as exc:
        return {"error": str(exc)}


def _fetch_provider_state(provider_url: str, logger: ApiLogger | None = None) -> dict[str, Any]:
    """Fetch all provider state in parallel sub-requests."""
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as c:
            stock_r = c.get(f"{provider_url}/api/stock")
            catalog_r = c.get(f"{provider_url}/api/catalog")
            orders_r = c.get(f"{provider_url}/api/orders?status=PENDING")
            day_r = c.get(f"{provider_url}/api/day/current")
        return {
            "stock": stock_r.json() if stock_r.is_success else [],
            "catalog": catalog_r.json() if catalog_r.is_success else {},
            "orders": orders_r.json() if orders_r.is_success else [],
            "day": day_r.json() if day_r.is_success else {},
        }
    except Exception as exc:
        return {"error": str(exc)}


def _fetch_manufacturer_state(mfr_url: str, logger: ApiLogger | None = None) -> dict[str, Any]:
    """Fetch all manufacturer state in a single call.

    Uses the bulk state endpoint (/api/state/all) to get all data needed
    for agent decision-making. Also fetches detailed inventory (demand +
    inbound quantities) for the 4-column inventory table. Falls back to
    fetching individually if bulk endpoint is not available.
    """
    state: dict[str, Any] = {}
    try:
        state = _get(f"{mfr_url}/api/state/all", logger=logger)
    except (httpx.HTTPError, KeyError):
        pass

    if "error" not in state and state:
        # Augment with detailed inventory (accepted_order_demand, pending_inbound_quantity),
        # warehouse capacity, and supplier pricing tiers for proactive ordering.
        try:
            inv_detail = _get(f"{mfr_url}/api/inventory/", logger=logger)
            if isinstance(inv_detail, list):
                state["inventory_detail"] = inv_detail
        except httpx.HTTPError:
            pass
        try:
            wh_cap = _get(f"{mfr_url}/api/inventory/capacity", logger=logger)
            if isinstance(wh_cap, dict):
                state["warehouse_capacity"] = wh_cap
        except httpx.HTTPError:
            pass
        try:
            suppliers_raw = _get(f"{mfr_url}/api/suppliers/", logger=logger)
            if isinstance(suppliers_raw, list):
                state["suppliers"] = suppliers_raw
        except httpx.HTTPError:
            pass
        # Also include capacity so format_state has assembly lines/workers data
        if "capacity" not in state:
            try:
                state["capacity"] = _get(f"{mfr_url}/api/capacity", logger=logger)
            except httpx.HTTPError:
                pass
        if "prices" not in state:
            try:
                prices_raw = _get(f"{mfr_url}/api/prices", logger=logger)
                state["prices"] = prices_raw.get("prices", {}) if isinstance(prices_raw, dict) else {}
            except httpx.HTTPError:
                pass
        return state

    try:
        prices_resp = _get(f"{mfr_url}/api/prices", logger=logger)
        prices_dict = prices_resp.get("prices", {}) if isinstance(prices_resp, dict) else {}
        inv_list = _get(f"{mfr_url}/api/inventory", logger=logger)
        # Convert inventory list to dict {material_name: quantity}
        inventory_dict = {}
        if isinstance(inv_list, list):
            for item in inv_list:
                if isinstance(item, dict):
                    name = item.get("product_name", item.get("name", ""))
                    qty = item.get("quantity", 0)
                    if name:
                        inventory_dict[name] = qty
        return {
            "day": _get(f"{mfr_url}/api/day/current", logger=logger),
            "capacity": _get(f"{mfr_url}/api/capacity", logger=logger),
            "inventory": inventory_dict,
            "sales_orders": _get(f"{mfr_url}/api/sales/orders?status=PENDING", logger=logger),
            "purchase_orders": _get(f"{mfr_url}/api/purchases", logger=logger),
            "production_status": _get(f"{mfr_url}/api/production/status", logger=logger),
            "prices": prices_dict,
        }
    except httpx.HTTPError as exc:
        return {"error": str(exc)}


def _format_state_for_prompt(state: dict[str, Any], role: str = "manufacturer") -> str:
    """Format pre-fetched state for embedding in an agent prompt.

    Eliminates the need for the agent to run assess commands.
    """
    if "error" in state:
        return f"\n⚠️ State unavailable: {state.get('error', 'Unknown error')}\n"

    if role == "manufacturer":
        capacity = state.get("capacity", {})
        inventory = state.get("inventory", {})
        sales_orders = state.get("sales_orders", {})
        purchase_orders = state.get("purchase_orders", {})
        prices = state.get("prices", {})
        day = state.get("day", {}).get("date", "unknown")

        # Build detail map from InventoryLevel objects (product_name → detail)
        inv_detail_raw = state.get("inventory_detail", [])
        inv_detail: dict[str, dict[str, Any]] = {}
        for item in inv_detail_raw:
            if isinstance(item, dict):
                name = item.get("product_name") or item.get("name", "")
                if name:
                    inv_detail[name] = item

        inv_lines = [
            "| Material | Stock | Needed (accepted orders) | Ordered (not delivered) | Storage Status |",
            "|-|-|-|-|-|",
        ]
        for mat, qty in inventory.items():
            qty_num = float(qty or 0)
            detail = inv_detail.get(mat, {})
            needed = float(detail.get("accepted_order_demand", 0))
            in_transit = float(detail.get("pending_inbound_quantity", 0))
            net_after_delivery = qty_num - needed + in_transit
            if qty_num < needed and in_transit == 0:
                status = "⚠️ CRITICAL"
            elif qty_num < needed:
                status = "⚠️ LOW (ordered)"
            elif net_after_delivery > qty_num * 2 and qty_num > 200:
                status = "⚡ EXCESS"
            else:
                status = "OK"
            inv_lines.append(
                f"| {mat} | {qty_num:.0f} | {needed:.0f} | {in_transit:.0f} | {status} |"
            )
        inv_table = "\n".join(inv_lines)

        pending = sales_orders.get("pending", [])
        pending_count = sales_orders.get("pending_count", 0)
        pending_sample = "\n".join([f"- {o['id']}: {o['model']}×{o['quantity']}" for o in pending[:5]])
        if pending_count > 5:
            pending_sample += f"\n- ... and {pending_count - 5} more"

        inbound = purchase_orders.get("inbound", [])
        inbound_lines = [
            f"- {p['product']}: {p['quantity']} units (due day {p.get('expected_arrival_day', '?')})"
            for p in inbound
        ]
        inbound_text = "\n".join(inbound_lines) if inbound_lines else "None"

        price_lines = [f"- {model}: ${price}" for model, price in prices.items()]
        prices_text = "\n".join(price_lines)

        # Warehouse capacity
        wh = state.get("warehouse_capacity", {})
        wh_total = wh.get("warehouse_capacity", "?")
        wh_used = wh.get("current_usage", "?")
        wh_avail = wh.get("available_capacity", "?")
        wh_pct = wh.get("usage_percentage", 0)
        wh_flag = " ⚠️ NEAR FULL" if float(wh_pct or 0) > 80 else ""
        wh_line = f"{wh_used}/{wh_total} units used ({wh_pct:.0f}%){wh_flag} — {wh_avail} units free"

        # Supplier pricing tiers for proactive bulk decisions
        suppliers_raw = state.get("suppliers", [])
        tier_lines: list[str] = []
        for sup in suppliers_raw:
            if not isinstance(sup, dict) or not sup.get("external_provider_url"):
                continue
            mat = sup.get("product_name") or sup.get("product_id", "?")
            tiers = sup.get("quantity_breaks") or []
            base = sup.get("unit_cost")
            lead = sup.get("lead_time_days", "?")
            if tiers:
                tier_str = ", ".join(f"{t['qty']}+→${t['price']}" for t in sorted(tiers, key=lambda t: t["qty"]))
                tier_lines.append(f"- {mat} ({sup.get('name', '?')}, {lead}d lead): base ${base} | tiers: {tier_str}")
            else:
                tier_lines.append(f"- {mat} ({sup.get('name', '?')}, {lead}d lead): ${base} flat")
        supplier_tiers_text = "\n".join(tier_lines) if tier_lines else "No external suppliers configured."

        lines_count = capacity.get('assembly_lines', capacity.get('lines', 1))
        workers_per_line = capacity.get('workers_per_line', capacity.get('workers', 1))
        shift_h = capacity.get('shift_hours', 8)
        daily_h = capacity.get('daily_hours', capacity.get('daily_assembly_hours', 8))

        return f"""
## Current State (Day {day})

**Production Capacity**: {lines_count} lines × {workers_per_line} workers/line × {shift_h}h = **{daily_h} hours/day**
*(hire-worker adds 1 worker to EVERY line; cost = rate × lines × shift_hours)*

**Warehouse**: {wh_line}
*(Do NOT order more than warehouse free space; check available before ordering)*

**Inventory Levels**:
{inv_table}

**External Supplier Tiers** (order in advance — lead time applies):
{supplier_tiers_text}

**PENDING Sales Orders** ({pending_count} total):
{pending_sample}

**Inbound Purchase Orders** (arriving):
{inbound_text}

**Wholesale Prices**:
{prices_text}

---
"""

    if role == "retailer":
        catalog = state.get("catalog", {})
        stock_raw = state.get("stock", [])
        orders_raw = state.get("orders", [])
        purchases_raw = state.get("purchases", [])
        day_val = state.get("day", {}).get("sim_day", state.get("day", {}).get("date", "?"))

        entries = catalog.get("entries", []) if isinstance(catalog, dict) else []
        stock_list = stock_raw if isinstance(stock_raw, list) else stock_raw.get("items", [])
        orders_list = orders_raw if isinstance(orders_raw, list) else orders_raw.get("orders", [])
        purchases_list = purchases_raw if isinstance(purchases_raw, list) else purchases_raw.get("orders", [])

        stock_lines = ["| Model | On Hand |", "|-|-|"]
        for s in stock_list:
            if isinstance(s, dict):
                stock_lines.append(f"| {s.get('product_name', '?')} | {s.get('quantity', 0)} |")
        stock_table = "\n".join(stock_lines)

        price_lines = [
            f"- {e.get('product_name', '?')}: ${e.get('retail_price', '?')}"
            for e in entries if isinstance(e, dict)
        ]
        prices_text = "\n".join(price_lines) if price_lines else "None"

        pending_cust = [o for o in orders_list if isinstance(o, dict) and o.get("status", "").upper() in ("PENDING", "BACKORDERED")]
        backorders = [o for o in orders_list if isinstance(o, dict) and o.get("status", "").upper() == "BACKORDERED"]
        inbound_pos = [p for p in purchases_list if isinstance(p, dict) and p.get("status", "").upper() in ("PENDING", "CONFIRMED", "IN_PROGRESS")]

        # Per-model backorder counts
        backorder_by_model: dict[str, int] = {}
        for o in backorders:
            m = o.get("product_name") or o.get("model", "?")
            backorder_by_model[m] = backorder_by_model.get(m, 0) + int(o.get("quantity", 1))

        # Per-model inbound totals (pending purchase orders from manufacturer)
        inbound_by_model: dict[str, int] = {}
        for p in inbound_pos:
            m = p.get("product_name") or p.get("model", "?")
            inbound_by_model[m] = inbound_by_model.get(m, 0) + int(p.get("quantity", 0))

        # Combined demand table: Stock | Backordered | Inbound | Net short
        stock_by_model: dict[str, int] = {
            s.get("product_name", "?"): int(s.get("quantity", 0))
            for s in stock_list if isinstance(s, dict)
        }
        all_models = sorted(set(list(stock_by_model) + list(backorder_by_model) + list(inbound_by_model)))
        demand_lines = ["| Model | On Hand | Backordered | Inbound (mfr) | Still Short |", "|-|-|-|-|-|"]
        for m in all_models:
            on_hand = stock_by_model.get(m, 0)
            bo = backorder_by_model.get(m, 0)
            inb = inbound_by_model.get(m, 0)
            short = max(0, bo - on_hand - inb)
            flag = " ⚠️" if short > 0 else ""
            demand_lines.append(f"| {m} | {on_hand} | {bo} | {inb} | {short}{flag} |")
        demand_table = "\n".join(demand_lines)

        return f"""
## Current State (Day {day_val})

**Demand & Stock Overview**:
{demand_table}

*(Still Short = backordered units not covered by current stock + inbound. Order at least this much to clear the backlog.)*

**Catalog Prices**:
{prices_text}

**Customer Orders**: {len(pending_cust)} pending/backordered total (of which {len(backorders)} backordered)

---
"""

    if role == "provider":
        catalog = state.get("catalog", {})
        stock_raw = state.get("stock", [])
        orders_raw = state.get("orders", [])
        day_val = state.get("day", {}).get("sim_day", state.get("day", {}).get("date", "?"))

        products = catalog.get("products", []) if isinstance(catalog, dict) else []
        stock_list = stock_raw if isinstance(stock_raw, list) else []
        orders_list = orders_raw if isinstance(orders_raw, list) else orders_raw.get("orders", [])

        stock_by_name = {s.get("product_name", ""): s.get("quantity", 0) for s in stock_list if isinstance(s, dict)}

        _STARTING = {
            "Control Board": 500, "Stepper Motor": 800, "Aluminum Frame": 300,
            "PLA Filament": 1000, "ABS Filament": 800, "LCD Screen": 200,
        }
        stock_lines = ["| Product | Current | Target | % |", "|-|-|-|-|"]
        for prod in products:
            if not isinstance(prod, dict):
                continue
            name = prod.get("name", "?")
            qty = stock_by_name.get(name, prod.get("stock_quantity", 0))
            target = _STARTING.get(name, 500)
            pct = int(qty / target * 100) if target else 0
            flag = " ⚠️" if pct < 30 else ""
            stock_lines.append(f"| {name} | {qty} | {target} | {pct}%{flag} |")
        stock_table = "\n".join(stock_lines)

        pending_count = len([o for o in orders_list if isinstance(o, dict)])

        return f"""
## Current State (Day {day_val})

**Stock vs Targets**:
{stock_table}

**Pending Orders**: {pending_count} awaiting fulfillment

---
"""

    return "\n"


# ── per-turn steps ────────────────────────────────────────────────────────────


def inject_customer_demand(
    retailer_cfg: dict[str, Any],
    scenario: dict[str, Any],
    day: int,
    retail_prices: dict[str, float],
    base_prices: dict[str, float],
    logger: ApiLogger | None = None,
) -> list[dict[str, Any]]:
    """Generate and inject demand orders into the retailer."""

    signal = get_day_signal(scenario, day)
    orders = generate_customer_demand(day, signal, retail_prices, base_prices)
    results = []
    for index, (model, qty) in enumerate(orders, 1):
        try:
            result = _post(
                f"{retailer_cfg['url']}/api/orders",
                {
                    "customer": f"synthetic-day-{day:03d}-{index:03d}",
                    "product_name": model,
                    "quantity": qty,
                },
                logger=logger,
            )
            results.append({"model": model, "qty": qty, "result": result})
        except httpx.HTTPError as exc:
            results.append({"model": model, "qty": qty, "error": str(exc)})
    return results


def forward_demand_via_retailer(
    retailer_cfg: dict[str, Any],
    demand_results: list[dict[str, Any]],
    logger: ApiLogger | None = None,
) -> list[dict[str, Any]]:
    """Forward BACKORDERED demand orders to the retailer's purchase endpoint.

    Consolidates per-model so one PO per model is placed per day instead of one
    per customer. This keeps the manufacturer order queue manageable while still
    ensuring all backordered demand is covered.

    Only forward orders that are BACKORDERED — orders already FULFILLED from
    retailer's stock don't need production.
    """
    # Aggregate backordered quantity per model
    model_qty: dict[str, int] = {}
    for order in demand_results:
        if "error" in order:
            continue
        order_data = order.get("result", {}).get("order", {})
        if order_data.get("status") != "BACKORDERED":
            continue
        model = order["model"]
        model_qty[model] = model_qty.get(model, 0) + order["qty"]

    results = []
    for model, qty in model_qty.items():
        try:
            result = _post(
                f"{retailer_cfg['url']}/api/purchases",
                {"product_name": model, "quantity": qty},
                logger=logger,
            )
            results.append({"model": model, "qty": qty, "result": result})
        except httpx.HTTPError as exc:
            results.append({"model": model, "qty": qty, "error": str(exc)})
    return results


def apply_provider_market_signal(
    provider_cfg: dict[str, Any],
    signal: dict[str, Any],
    logger: ApiLogger | None = None,
) -> Any:
    """Best-effort push of market signal into provider order intake."""

    try:
        return _post(
            f"{provider_cfg['url']}/api/day/signal",
            {
                "supply_modifier": float(signal.get("supply_modifier", 1.0)),
                "lead_time_modifier": float(signal.get("lead_time_modifier", 1.0)),
            },
            logger=logger,
        )
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": str(exc)}


def run_role_agent(
    role: str,
    role_cfg: dict[str, Any],
    day: int,
    signal: dict[str, Any],
    state_context: str = "",
    fast_mode: bool = False,
) -> str:
    """Run the stub, scripted, or claude agent for a role; return log output."""

    skill_file: str | None = role_cfg.get("skill") or None
    cwd = role_cfg.get("path", ".")
    model: str = os.environ.get("CLAUDE_MODEL") or role_cfg.get("model", "claude-haiku-4-5-20251001")

    if fast_mode and skill_file:
        # Scripted agent replaces claude subprocess entirely
        return run_agent(
            role, day, "", skill_file, cwd=cwd, model=model,
            fast_mode=True, role_cfg=role_cfg, signal=signal,
        )

    if skill_file:
        prompt = build_prompt(role, day, signal, skill_file, state_context=state_context)
    else:
        prompt = f"[stub] {role} day {day}"
    return run_agent(role, day, prompt, skill_file, cwd=cwd, model=model)


def advance_app(app_url: str, app_name: str, logger: ApiLogger | None = None) -> Any:
    """Advance one app day and return the summary.

    Week 7 apps mostly use ``/api/day/advance``. The manufacturer
    backend exposes ``/api/simulation/advance-day`` instead, so we
    fallback to that route on 404 for compatibility.
    """

    try:
        with httpx.Client(timeout=ADVANCE_TIMEOUT) as client:
            r = client.post(f"{app_url}/api/day/advance", json={})
            try:
                result = r.json() if r.content else {}
            except Exception:
                result = {}
            if logger:
                logger.log("POST", f"{app_url}/api/day/advance", {}, r.status_code, result)
            r.raise_for_status()
        print(f"  [{app_name}] day advanced → {result}")
        return result
    except httpx.HTTPError as exc:
        response = getattr(exc, "response", None)
        if response is not None and response.status_code == 404:
            try:
                with httpx.Client(timeout=ADVANCE_TIMEOUT) as fc:
                    fr = fc.post(f"{app_url}/api/simulation/advance-day", json={})
                    result = fr.json() if fr.content else {}
                    if logger:
                        logger.log("POST", f"{app_url}/api/simulation/advance-day", {}, fr.status_code, result)
                    fr.raise_for_status()
                print(f"  [{app_name}] day advanced → {result}")
                return result
            except httpx.HTTPError as fallback_exc:
                print(f"  [{app_name}] advance FAILED: {fallback_exc}", file=sys.stderr)
                return {"error": str(fallback_exc)}
        print(f"  [{app_name}] advance FAILED: {exc}", file=sys.stderr)
        return {"error": str(exc)}


# ── run initialisation ───────────────────────────────────────────────────────


def _initialize_run(config: dict[str, Any]) -> None:
    """One-time checks before the day loop.

    Reads the manufacturer's current configuration and warns about any
    conditions that would produce misleading results (missing prices,
    unexpected demand generator state). Does NOT modify any settings —
    those are the operator's responsibility.
    """
    mfr_url = config.get("manufacturer", {}).get("url")
    if not mfr_url:
        return

    try:
        cfg = _get(f"{mfr_url}/api/config/")
    except httpx.HTTPError as exc:
        print(f"  [init] WARNING: could not reach manufacturer config: {exc}")
        return

    if cfg.get("internal_demand_enabled"):
        print(
            "  [init] WARNING: internal demand generator is ON — "
            "the manufacturer will create random ManufacturingOrders each day "
            "alongside retailer SalesOrders. Disable it in Settings if unintended."
        )

    prices_data: dict[str, Any] = {}
    try:
        prices_data = _get(f"{mfr_url}/api/prices")
    except httpx.HTTPError as exc:
        print(f"  [init] WARNING: could not check wholesale prices: {exc}")
        return
    prices = prices_data.get("prices", {})
    if not prices:
        # Try to initialize prices
        try:
            _post(f"{mfr_url}/api/config/init-prices", {})
            prices_data = _get(f"{mfr_url}/api/prices")
            prices = prices_data.get("prices", {})
        except httpx.HTTPError:
            pass
    if not prices:
        print("  [init] WARNING: no wholesale prices configured — revenue will be $0")
    else:
        zero = [k for k, v in prices.items() if float(v or 0) == 0]
        if zero:
            print(f"  [init] WARNING: $0 wholesale price for: {', '.join(zero)}")
        else:
            print(f"  [init] prices OK: {', '.join(f'{k}=${v}' for k, v in prices.items())}")


# ── main turn ─────────────────────────────────────────────────────────────────


def _prefetch_all_state(
    retailers: list[dict[str, Any]],
    mfr: dict[str, Any],
    providers: list[dict[str, Any]],
    api_logger: ApiLogger | None,
) -> dict[str, tuple[dict[str, Any], str]]:
    """Fetch state for all roles concurrently; return {role_name: (state, context_str)}."""

    def fetch_mfr() -> tuple[str, dict[str, Any], str]:
        name = mfr.get("name", "manufacturer")
        if not mfr.get("url"):
            return name, {}, ""
        try:
            state = _fetch_manufacturer_state(mfr["url"], logger=api_logger)
            ctx = _format_state_for_prompt(state, role="manufacturer")
        except Exception as exc:
            state = {"error": str(exc)}
            ctx = f"\n⚠️ State fetch failed: {exc}\n"
        return name, state, ctx

    def fetch_retailer(r_cfg: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        name = r_cfg.get("name", "retailer")
        try:
            state = _fetch_retailer_state(r_cfg["url"], logger=api_logger)
            ctx = _format_state_for_prompt(state, role="retailer")
        except Exception as exc:
            state = {"error": str(exc)}
            ctx = f"\n⚠️ State fetch failed: {exc}\n"
        return name, state, ctx

    def fetch_provider(p_cfg: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        name = p_cfg.get("name", "provider")
        try:
            state = _fetch_provider_state(p_cfg["url"], logger=api_logger)
            ctx = _format_state_for_prompt(state, role="provider")
        except Exception as exc:
            state = {"error": str(exc)}
            ctx = f"\n⚠️ State fetch failed: {exc}\n"
        return name, state, ctx

    results: dict[str, tuple[dict[str, Any], str]] = {}
    tasks = [fetch_mfr] + [lambda r=r: fetch_retailer(r) for r in retailers] + [lambda p=p: fetch_provider(p) for p in providers]

    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as ex:
        for fut in as_completed([ex.submit(t) for t in tasks]):
            name, state, ctx = fut.result()
            results[name] = (state, ctx)

    return results


def _summarize_agent_output(output: str, max_length: int = 300) -> str:
    """Extract the first line of agent output, limit to max_length characters.

    Agents follow the skill instruction to start with a one-line decision summary,
    so we just take the first non-empty line.
    """
    lines = [line.strip() for line in output.strip().split('\n') if line.strip()]
    if not lines:
        return "(no output)"

    summary = lines[0]
    if len(summary) > max_length:
        summary = summary[:max_length].rstrip() + "…"
    return summary


def run_day(
    config: dict[str, Any],
    scenario: dict[str, Any],
    day: int,
) -> dict[str, Any]:
    """Execute one complete simulation turn.

    State is pre-fetched concurrently for all roles, then agents run
    sequentially: retailer → manufacturer → provider. After the retailer
    agent completes, manufacturer state is re-fetched so the manufacturer
    agent sees any SalesOrders placed by the retailer during its turn.
    Fast mode replaces claude with scripted decision logic.
    """

    fast_mode: bool = os.environ.get("FAST_MODE", "").lower() in ("1", "true", "yes")

    print(f"\n=== Day {day} {'[fast-mode]' if fast_mode else ''} ===")
    signal = get_day_signal(scenario, day)
    summary: dict[str, Any] = {"day": day, "signal": signal, "fast_mode": fast_mode}

    retailers: list[dict[str, Any]] = config.get("retailers", [])
    mfr: dict[str, Any] = config.get("manufacturer", {})
    providers: list[dict[str, Any]] = config.get("providers", [])
    mfr_name = mfr.get("name", "manufacturer")

    api_logger = ApiLogger(day)

    # ── 0. Apply scenario signal to providers ─────────────────────────────────
    for p_cfg in providers:
        apply_provider_market_signal(p_cfg, signal, logger=api_logger)

    # ── 1. Inject demand at each retailer ─────────────────────────────────────
    demand_results: list[list[dict[str, Any]]] = []
    for r_cfg in retailers:
        try:
            retail_prices = _retailer_base_prices(r_cfg["url"], logger=api_logger)
        except httpx.HTTPError:
            retail_prices = {}
        demand_results.append(
            inject_customer_demand(r_cfg, scenario, day, retail_prices, retail_prices, logger=api_logger)
        )
    summary["demand_injected"] = demand_results

    # ── 1.5. Forward backordered demand to retailer's purchase service ─────────
    sales_forward_results = []
    for i, r_cfg in enumerate(retailers):
        sales_forward_results.append(
            forward_demand_via_retailer(r_cfg, demand_results[i], logger=api_logger)
        )
    summary["sales_forwarded"] = sales_forward_results

    # ── 2. Determine execution mode: sequential or parallel ────────────────────
    # Default: sequential (retailer → manufacturer → provider).
    # Override via PARALLEL_AGENTS env var (set by the UI) or the scenario
    # JSON field "parallel_agents": true. Env var takes precedence.
    # Parallel is faster but agents act on pre-fetched state and don't see
    # each other's writes within the same turn.
    env_parallel = os.environ.get("PARALLEL_AGENTS", "").lower()
    if env_parallel in ("1", "true", "yes"):
        parallel_agents: bool = True
    elif env_parallel in ("0", "false", "no"):
        parallel_agents = False
    else:
        parallel_agents = bool(scenario.get("parallel_agents", False))
    agent_outputs: dict[str, str] = {}

    if parallel_agents:
        # ── 2a. Parallel: pre-fetch state for all roles once ──────────────────
        print("  [engine] pre-fetching state for all roles…")
        state_map = _prefetch_all_state(retailers, mfr, providers, api_logger)

        print("  [engine] running agents in parallel (parallel_agents=true in scenario)")
        all_roles: list[tuple[str, dict[str, Any]]] = (
            [(r_cfg.get("name", "retailer"), r_cfg) for r_cfg in retailers]
            + [(mfr_name, mfr)]
            + [(p_cfg.get("name", "provider"), p_cfg) for p_cfg in providers]
        )
        def _run_one(role: str, role_cfg: dict[str, Any]) -> tuple[str, str]:
            _, ctx = state_map.get(role, ({}, ""))
            out = run_role_agent(role, role_cfg, day, signal, state_context=ctx, fast_mode=fast_mode)
            return role, out

        with ThreadPoolExecutor(max_workers=len(all_roles) or 1) as ex:
            for fut in as_completed([ex.submit(_run_one, n, c) for n, c in all_roles]):
                role_name, output = fut.result()
                agent_outputs[role_name] = output
                print(f"  [{role_name}] agent: {output.strip()[:80]}")
    else:
        # ── 2b. Sequential: fetch state for each agent just before it runs ────
        # Retailer agents first
        for r_cfg in retailers:
            role_name = r_cfg.get("name", "retailer")
            try:
                state = _fetch_retailer_state(r_cfg["url"], logger=api_logger)
                ctx = _format_state_for_prompt(state, role="retailer")
            except Exception as exc:
                state = {"error": str(exc)}
                ctx = f"\n⚠️ State fetch failed: {exc}\n"
            output = run_role_agent(role_name, r_cfg, day, signal, state_context=ctx, fast_mode=fast_mode)
            agent_outputs[role_name] = output
            print(f"  [{role_name}] agent: {_summarize_agent_output(output)}")

        # Manufacturer agent (fetch fresh state after retailer actions)
        if mfr.get("url"):
            try:
                mfr_state = _fetch_manufacturer_state(mfr["url"], logger=api_logger)
                mfr_ctx = _format_state_for_prompt(mfr_state, role="manufacturer")
            except Exception as exc:
                print(f"  [engine] WARNING: manufacturer state fetch failed: {exc}")
                mfr_state = {"error": str(exc)}
                mfr_ctx = f"\n⚠️ State fetch failed: {exc}\n"
        else:
            mfr_state = {}
            mfr_ctx = ""
        mfr_output = run_role_agent(mfr_name, mfr, day, signal, state_context=mfr_ctx, fast_mode=fast_mode)
        agent_outputs[mfr_name] = mfr_output
        print(f"  [{mfr_name}] agent: {mfr_output.strip()[:80]}")

        # Provider agents last (see purchase orders placed by manufacturer)
        for p_cfg in providers:
            role_name = p_cfg.get("name", "provider")
            try:
                state = _fetch_provider_state(p_cfg["url"], logger=api_logger)
                ctx = _format_state_for_prompt(state, role="provider")
            except Exception as exc:
                state = {"error": str(exc)}
                ctx = f"\n⚠️ State fetch failed: {exc}\n"
            output = run_role_agent(role_name, p_cfg, day, signal, state_context=ctx, fast_mode=fast_mode)
            agent_outputs[role_name] = output
            print(f"  [{role_name}] agent: {output.strip()[:80]}")

    summary["agent_outputs"] = {k: v[:200] for k, v in agent_outputs.items()}

    # ── 4. Advance: retailer → manufacturer → providers (order matters) ────────
    advance_results: dict[str, Any] = {}
    for r_cfg in retailers:
        advance_results[r_cfg.get("name", "retailer")] = advance_app(
            r_cfg["url"], r_cfg.get("name", "retailer"), logger=api_logger
        )
    advance_results[mfr_name] = advance_app(mfr["url"], mfr_name, logger=api_logger)
    for p_cfg in providers:
        advance_results[p_cfg.get("name", "provider")] = advance_app(
            p_cfg["url"], p_cfg.get("name", "provider"), logger=api_logger
        )

    summary["advance_results"] = advance_results

    metrics = snapshot_metrics(config, scenario, day, signal, logger=api_logger)
    append_metrics(metrics)
    summary["metrics"] = metrics
    print(f"  [summary] {summarize_metrics(metrics)}")
    return summary






# ── entry point ───────────────────────────────────────────────────────────────


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Usage: python -m engine.turn_engine <config.json> <scenario.json> <num_days>")
        return 1

    config_path = Path(argv[0])
    scenario_path = Path(argv[1])
    try:
        num_days = int(argv[2])
    except ValueError:
        print(f"num_days must be an integer, got {argv[2]!r}")
        return 1

    if not config_path.exists():
        print(f"Config not found: {config_path}")
        return 1
    if not scenario_path.exists():
        print(f"Scenario not found: {scenario_path}")
        return 1

    config = json.loads(config_path.read_text(encoding="utf-8"))
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))

    print(f"Turn engine — scenario: {scenario.get('scenario_name', 'unnamed')}")
    print(f"Running {num_days} day(s).")

    _initialize_run(config)

    for day in range(1, num_days + 1):
        run_day(config, scenario, day)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
