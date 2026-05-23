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
"""

from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from engine.api_logger import ApiLogger
from engine.demand import generate_customer_demand, get_day_signal
from engine.agent_runner import build_prompt, run_agent
from engine.metrics import append_metrics, snapshot_metrics, summarize_metrics


DEFAULT_TIMEOUT = 10.0  # seconds for routine API calls

# ── State cache for within-day queries ────────────────────────────────────────
_state_cache: dict[str, dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _get_cached_state(url: str, logger: ApiLogger | None = None) -> dict[str, Any]:
    """Get cached state or fetch and cache it."""
    with _cache_lock:
        if url in _state_cache:
            return _state_cache[url]

        state = _fetch_manufacturer_state(url, logger=logger)
        _state_cache[url] = state
        return state


def _clear_state_cache() -> None:
    """Clear state cache (called at start of new day)."""
    with _cache_lock:
        _state_cache.clear()


# ── helpers ──────────────────────────────────────────────────────────────────


def _post(url: str, payload: dict[str, Any], logger: ApiLogger | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        r = client.post(url, json=payload)
        if logger:
            logger.log("POST", url, payload, r.status_code, r.json())
        r.raise_for_status()
    return dict(r.json())


def _get(url: str, logger: ApiLogger | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        r = client.get(url)
        if logger:
            logger.log("GET", url, None, r.status_code, r.json())
        r.raise_for_status()
    return dict(r.json())


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


def _fetch_manufacturer_state(mfr_url: str, logger: ApiLogger | None = None) -> dict[str, Any]:
    """Fetch all manufacturer state in a single call.

    Uses the bulk state endpoint (/api/state/all) to get all data needed
    for agent decision-making. Falls back to fetching individually if bulk
    endpoint is not available.
    """
    try:
        # Try bulk endpoint first (Option C)
        state = _get(f"{mfr_url}/api/state/all", logger=logger)
        if "error" not in state:
            return state
    except (httpx.HTTPError, KeyError):
        pass

    # Fallback: fetch individually (Option B)
    try:
        return {
            "day": _get(f"{mfr_url}/api/day/current", logger=logger),
            "capacity": _get(f"{mfr_url}/api/capacity", logger=logger),
            "inventory": _get(f"{mfr_url}/api/inventory", logger=logger),
            "sales_orders": _get(f"{mfr_url}/api/sales/orders?status=PENDING", logger=logger),
            "purchase_orders": _get(f"{mfr_url}/api/purchases", logger=logger),
            "production_status": _get(f"{mfr_url}/api/production/status", logger=logger),
            "prices": _get(f"{mfr_url}/api/prices", logger=logger),
        }
    except httpx.HTTPError as exc:
        return {"error": str(exc)}


def _format_state_for_prompt(state: dict[str, Any], role: str = "manufacturer") -> str:
    """Format state data for inclusion in agent prompt.

    Returns formatted markdown with current state as context for the agent,
    so it doesn't need to make repeated state-check API calls.
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

        # Build inventory table
        inv_lines = ["| Material | Current | Status |", "|-|-|-|"]
        for mat, qty in inventory.items():
            inv_lines.append(f"| {mat} | {qty} | OK |")
        inv_table = "\n".join(inv_lines)

        # Build pending orders summary
        pending = sales_orders.get("pending", [])
        pending_count = sales_orders.get("pending_count", 0)
        pending_sample = "\n".join([f"- {o['id']}: {o['model']}×{o['quantity']}" for o in pending[:5]])
        if pending_count > 5:
            pending_sample += f"\n- ... and {pending_count - 5} more"

        # Build inbound purchases summary
        inbound = purchase_orders.get("inbound", [])
        inbound_lines = []
        for p in inbound:
            inbound_lines.append(f"- {p['product']}: {p['quantity']} units (due day {p.get('expected_arrival_day', '?')})")
        inbound_text = "\n".join(inbound_lines) if inbound_lines else "None"

        # Build prices
        price_lines = [f"- {model}: ${price}" for model, price in prices.items()]
        prices_text = "\n".join(price_lines)

        return f"""
## Current State (Day {day})

**Production Capacity**: {capacity.get('lines', 1)} lines × {capacity.get('workers_per_line', 1)} workers × {capacity.get('shift_hours', 8)}h = **{capacity.get('daily_hours', 8)} hours/day**

**Inventory Levels**:
{inv_table}

**PENDING Sales Orders** ({pending_count} total):
{pending_sample}

**Inbound Purchase Orders** (arriving):
{inbound_text}

**Wholesale Prices**:
{prices_text}

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


def forward_demand_to_manufacturer(
    mfr_cfg: dict[str, Any],
    retailer_name: str,
    demand_results: list[dict[str, Any]],
    logger: ApiLogger | None = None,
) -> list[dict[str, Any]]:
    """Forward each demand order to the manufacturer as a SalesOrder.

    This bridges the gap in Phase 1 where the retailer (with no skill file)
    doesn't auto-restock from the manufacturer. The turn engine directly
    POSTs sales orders to /api/sales/orders at the manufacturer.

    Parameters
    ----------
    mfr_cfg:
        Manufacturer config from sim.json with 'url' key.
    retailer_name:
        Name of the retailer to set as source of sales order.
    demand_results:
        List of demand order results from inject_customer_demand.
    logger:
        Optional API logger to record all calls.

    Returns
    -------
    List of results for each order forwarded. Each item has keys:
    - "model", "qty": order details
    - "result": response from manufacturer (on success)
    - "error": error message (on failure)
    """
    results = []
    for order in demand_results:
        if "error" in order:
            # Skip orders that failed to place at retailer
            continue
        try:
            result = _post(
                f"{mfr_cfg['url']}/api/sales/orders",
                {
                    "retailer": retailer_name,
                    "model": order["model"],
                    "quantity": order["qty"],
                },
                logger=logger,
            )
            results.append({"model": order["model"], "qty": order["qty"], "result": result})
        except httpx.HTTPError as exc:
            results.append({"model": order["model"], "qty": order["qty"], "error": str(exc)})
    return results


def apply_provider_market_signal(
    provider_cfg: dict[str, Any],
    signal: dict[str, Any],
    logger: ApiLogger | None = None,
) -> dict[str, Any]:
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
) -> str:
    """Run the stub or claude agent for a role; return log output.

    Parameters
    ----------
    state_context:
        Pre-fetched state formatted for embedding in prompt.
        If provided, agent reads this instead of making state-check calls.
    """

    import os
    skill_file: str | None = role_cfg.get("skill") or None
    cwd = role_cfg.get("path", ".")
    # Use env var if set, otherwise fall back to config, then default
    model: str = os.environ.get("CLAUDE_MODEL") or role_cfg.get("model", "claude-haiku-4-5-20251001")
    if skill_file:
        prompt = build_prompt(role, day, signal, skill_file, state_context=state_context)
    else:
        prompt = f"[stub] {role} day {day}"
    return run_agent(role, day, prompt, skill_file, cwd=cwd, model=model)


def advance_app(app_url: str, app_name: str, logger: ApiLogger | None = None) -> dict[str, Any]:
    """Advance one app day and return the summary.

    Week 7 apps mostly use ``/api/day/advance``. The manufacturer
    backend exposes ``/api/simulation/advance-day`` instead, so we
    fallback to that route on 404 for compatibility.
    """

    try:
        result = _post(f"{app_url}/api/day/advance", {}, logger=logger)
        print(f"  [{app_name}] day advanced → {result}")
        return result
    except httpx.HTTPError as exc:
        response = getattr(exc, "response", None)
        if response is not None and response.status_code == 404:
            try:
                result = _post(f"{app_url}/api/simulation/advance-day", {}, logger=logger)
                print(f"  [{app_name}] day advanced → {result}")
                return result
            except httpx.HTTPError as fallback_exc:
                print(f"  [{app_name}] advance FAILED: {fallback_exc}", file=sys.stderr)
                return {"error": str(fallback_exc)}
        print(f"  [{app_name}] advance FAILED: {exc}", file=sys.stderr)
        return {"error": str(exc)}


# ── main turn ─────────────────────────────────────────────────────────────────


def run_day(
    config: dict[str, Any],
    scenario: dict[str, Any],
    day: int,
) -> dict[str, Any]:
    """Execute one complete simulation turn.

    Returns a summary dict with per-role results.
    """

    print(f"\n=== Day {day} ===")
    signal = get_day_signal(scenario, day)
    summary: dict[str, Any] = {"day": day, "signal": signal}

    retailers: list[dict[str, Any]] = config.get("retailers", [])
    mfr: dict[str, Any] = config.get("manufacturer", {})
    providers: list[dict[str, Any]] = config.get("providers", [])

    # Initialize API logger for this day
    api_logger = ApiLogger(day)

    # ── 0. Apply scenario signal to providers before agents place orders ──────
    provider_signal_results = []
    for p_cfg in providers:
        provider_signal_results.append(
            apply_provider_market_signal(p_cfg, signal, logger=api_logger)
        )
    summary["provider_signal_results"] = provider_signal_results

    # ── 1. Inject demand at each retailer ────────────────────────────────────
    demand_results = []
    base_prices_cache: dict[str, dict[str, float]] = {}
    for r_cfg in retailers:
        r_url = r_cfg["url"]
        try:
            retail_prices = _retailer_base_prices(r_url, logger=api_logger)
        except httpx.HTTPError:
            retail_prices = {}
        # Use current retail prices as both actual and base prices.
        # (Week 8 will snapshot seed prices separately for elasticity.)
        base_prices_cache[r_url] = retail_prices
        demand_results.append(
            inject_customer_demand(r_cfg, scenario, day, retail_prices, retail_prices, logger=api_logger)
        )
    summary["demand_injected"] = demand_results

    # ── 1.5. Forward demand to manufacturer (Phase 1 bridge) ──────────────────
    sales_forward_results = []
    for i, r_cfg in enumerate(retailers):
        r_name = r_cfg.get("name", "retailer")
        sales_forward_results.append(
            forward_demand_to_manufacturer(mfr, r_name, demand_results[i], logger=api_logger)
        )
    summary["sales_forwarded"] = sales_forward_results

    # ── 2. Role decision hooks (parallelized where possible) ────────────────────
    # Clear state cache at start of day
    _clear_state_cache()
    agent_outputs = {}

    # Fetch manufacturer state upfront (Option B/C: embed in prompt + cache)
    mfr_name = mfr.get("name", "manufacturer")
    mfr_state_context = ""
    if mfr and "url" in mfr:
        try:
            mfr_state = _get_cached_state(mfr["url"], logger=api_logger)
            mfr_state_context = _format_state_for_prompt(mfr_state, role="manufacturer")
            print(f"  [{mfr_name}] state pre-fetched (Option B/C + cache)")
        except Exception as e:
            print(f"  [{mfr_name}] state pre-fetch failed: {e}", file=sys.stderr)

    # Run retailer and provider agents in parallel (they don't depend on each other)
    # Manufacturer must run sequentially after retailers (depends on demand)
    with ThreadPoolExecutor(max_workers=2) as executor:
        retailer_futures = {}
        for r_cfg in retailers:
            role = r_cfg.get("name", "retailer")
            retailer_futures[role] = executor.submit(run_role_agent, role, r_cfg, day, signal)

        provider_futures = {}
        for p_cfg in providers:
            role = p_cfg.get("name", "provider")
            provider_futures[role] = executor.submit(run_role_agent, role, p_cfg, day, signal)

        # Collect retailer results (must wait before manufacturer runs)
        for role, future in retailer_futures.items():
            agent_outputs[role] = future.result()
            print(f"  [{role}] agent: {agent_outputs[role].strip()[:80]}")

    # Run manufacturer (after retailers, but can run in parallel with providers)
    agent_outputs[mfr_name] = run_role_agent(mfr_name, mfr, day, signal, state_context=mfr_state_context)
    print(f"  [{mfr_name}] agent: {agent_outputs[mfr_name].strip()[:80]}")

    # Collect provider results (they may already be done if running in parallel)
    with ThreadPoolExecutor(max_workers=2) as executor:
        provider_futures = {}
        for p_cfg in providers:
            role = p_cfg.get("name", "provider")
            # Check if already running from earlier parallel execution
            if role not in agent_outputs:
                provider_futures[role] = executor.submit(run_role_agent, role, p_cfg, day, signal)

        for role, future in provider_futures.items():
            agent_outputs[role] = future.result()
            print(f"  [{role}] agent: {agent_outputs[role].strip()[:80]}")

    summary["agent_outputs"] = {k: v[:200] for k, v in agent_outputs.items()}

    # ── 3. Advance: retailer → manufacturer → providers ───────────────────────
    advance_results = {}
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


def apply_assembly_config(mfr_url: str, logger: ApiLogger | None = None) -> dict[str, Any]:
    """Apply assembly configuration from environment variables to the manufacturer.

    Environment variables:
    - ASSEMBLY_LINES: number of parallel assembly lines
    - WORKERS_PER_LINE: workers per line
    - SHIFT_HOURS: hours per shift
    """

    assembly_lines = os.environ.get("ASSEMBLY_LINES")
    workers_per_line = os.environ.get("WORKERS_PER_LINE")
    shift_hours = os.environ.get("SHIFT_HOURS")

    if not (assembly_lines or workers_per_line or shift_hours):
        return {}

    try:
        payload = {}
        if assembly_lines:
            payload["assembly_lines"] = int(assembly_lines)
        if workers_per_line:
            payload["workers_per_line"] = int(workers_per_line)
        if shift_hours:
            payload["shift_hours"] = float(shift_hours)

        result = _put(f"{mfr_url}/api/config/", payload, logger=logger)
        return result
    except (ValueError, httpx.HTTPError) as exc:
        return {"error": str(exc)}


def apply_scenario_config(mfr_url: str, scenario: dict[str, Any], logger: ApiLogger | None = None) -> dict[str, Any]:
    """Apply scenario configuration (assembly and costs) to the manufacturer if config is at defaults.

    Only applies recommended_assembly and recommended_costs from the scenario JSON if the
    current configuration matches the starter profile defaults. This prevents overriding
    user customizations.

    Environment variables take precedence over scenario values.
    """
    try:
        current_config = _get(f"{mfr_url}/api/config/", logger=logger)
    except httpx.HTTPError as exc:
        return {"error": str(exc)}

    # Check if current config is at starter defaults (user hasn't customized)
    # by comparing key assembly and cost fields
    is_at_defaults = (
        current_config.get("assembly_lines") == 1
        and current_config.get("workers_per_line") == 1
        and current_config.get("shift_hours") == 8.0
        and current_config.get("cost_per_assembly_line") == 50000.0
        and current_config.get("cost_per_worker_per_hour") == 50.0
        and current_config.get("max_workers_per_line") == 10
    )

    if not is_at_defaults:
        # User has customized config; don't override
        return current_config

    payload = {}

    recommended_assembly = scenario.get("recommended_assembly", {})
    if recommended_assembly:
        if "assembly_lines" in recommended_assembly:
            payload["assembly_lines"] = recommended_assembly["assembly_lines"]
        if "workers_per_line" in recommended_assembly:
            payload["workers_per_line"] = recommended_assembly["workers_per_line"]
        if "shift_hours" in recommended_assembly:
            payload["shift_hours"] = recommended_assembly["shift_hours"]

    recommended_costs = scenario.get("recommended_costs", {})
    if recommended_costs:
        if "cost_per_assembly_line" in recommended_costs:
            payload["cost_per_assembly_line"] = recommended_costs["cost_per_assembly_line"]
        if "cost_per_worker_per_hour" in recommended_costs:
            payload["cost_per_worker_per_hour"] = recommended_costs["cost_per_worker_per_hour"]
        if "max_workers_per_line" in recommended_costs:
            payload["max_workers_per_line"] = recommended_costs["max_workers_per_line"]

    if not payload:
        return current_config

    try:
        result = _put(f"{mfr_url}/api/config/", payload, logger=logger)
        return result
    except httpx.HTTPError as exc:
        return {"error": str(exc)}


def _put(url: str, payload: dict[str, Any], logger: ApiLogger | None = None) -> dict[str, Any]:
    """PUT request to update resource."""
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        r = client.put(url, json=payload)
        if logger:
            logger.log("PUT", url, payload, r.status_code, r.json())
        r.raise_for_status()
    return dict(r.json())


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

    # Apply assembly configuration from environment variables only
    # (Scenario config is applied via UI, not automatically)
    mfr = config.get("manufacturer", {})
    if mfr and "url" in mfr:
        apply_assembly_config(mfr["url"])

    for day in range(1, num_days + 1):
        run_day(config, scenario, day)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
