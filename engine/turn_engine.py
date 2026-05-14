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
import sys
from pathlib import Path
from typing import Any

import httpx

from engine.demand import generate_customer_demand, get_day_signal
from engine.agent_runner import build_prompt, run_agent


DEFAULT_TIMEOUT = 10.0  # seconds for routine API calls


# ── helpers ──────────────────────────────────────────────────────────────────


def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
    return dict(r.json())


def _get(url: str) -> dict[str, Any]:
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        r = client.get(url)
        r.raise_for_status()
    return dict(r.json())


def _retailer_base_prices(retailer_url: str) -> dict[str, float]:
    """Fetch the retailer's current catalog prices (used as demand baseline)."""
    data = _get(f"{retailer_url}/api/catalog")
    return {
        entry["product_name"]: float(entry["retail_price"])
        for entry in data.get("catalog", [])
        if isinstance(entry.get("retail_price"), (int, float))
    }


# ── per-turn steps ────────────────────────────────────────────────────────────


def inject_customer_demand(
    retailer_cfg: dict[str, Any],
    scenario: dict[str, Any],
    day: int,
    retail_prices: dict[str, float],
    base_prices: dict[str, float],
) -> list[dict[str, Any]]:
    """Generate and inject demand orders into the retailer."""

    signal = get_day_signal(scenario, day)
    orders = generate_customer_demand(day, signal, retail_prices, base_prices)
    results = []
    for model, qty in orders:
        try:
            result = _post(
                f"{retailer_cfg['url']}/api/orders",
                {"product_name": model, "quantity": qty},
            )
            results.append({"model": model, "qty": qty, "result": result})
        except httpx.HTTPError as exc:
            results.append({"model": model, "qty": qty, "error": str(exc)})
    return results


def run_role_agent(
    role: str,
    role_cfg: dict[str, Any],
    day: int,
    signal: dict[str, Any],
) -> str:
    """Run the stub or claude agent for a role; return log output."""

    skill_file: str | None = role_cfg.get("skill") or None
    cwd = role_cfg.get("path", ".")
    if skill_file:
        prompt = build_prompt(role, day, signal, skill_file)
    else:
        prompt = f"[stub] {role} day {day}"
    return run_agent(role, day, prompt, skill_file, cwd=cwd)


def advance_app(app_url: str, app_name: str) -> dict[str, Any]:
    """POST /api/day/advance to one app; return the summary."""

    try:
        result = _post(f"{app_url}/api/day/advance", {})
        print(f"  [{app_name}] day advanced → {result}")
        return result
    except httpx.HTTPError as exc:
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

    # ── 1. Inject demand at each retailer ────────────────────────────────────
    demand_results = []
    base_prices_cache: dict[str, dict[str, float]] = {}
    for r_cfg in retailers:
        r_url = r_cfg["url"]
        try:
            retail_prices = _retailer_base_prices(r_url)
        except httpx.HTTPError:
            retail_prices = {}
        # Use current retail prices as both actual and base prices.
        # (Week 8 will snapshot seed prices separately for elasticity.)
        base_prices_cache[r_url] = retail_prices
        demand_results.append(
            inject_customer_demand(r_cfg, scenario, day, retail_prices, retail_prices)
        )
    summary["demand_injected"] = demand_results

    # ── 2. Role decision hooks ────────────────────────────────────────────────
    agent_outputs = {}
    for r_cfg in retailers:
        role = r_cfg.get("name", "retailer")
        agent_outputs[role] = run_role_agent(role, r_cfg, day, signal)
        print(f"  [{role}] agent: {agent_outputs[role].strip()[:80]}")

    mfr_name = mfr.get("name", "manufacturer")
    agent_outputs[mfr_name] = run_role_agent(mfr_name, mfr, day, signal)
    print(f"  [{mfr_name}] agent: {agent_outputs[mfr_name].strip()[:80]}")

    for p_cfg in providers:
        role = p_cfg.get("name", "provider")
        agent_outputs[role] = run_role_agent(role, p_cfg, day, signal)
        print(f"  [{role}] agent: {agent_outputs[role].strip()[:80]}")

    summary["agent_outputs"] = {k: v[:200] for k, v in agent_outputs.items()}

    # ── 3. Advance: retailer → manufacturer → providers ───────────────────────
    advance_results = {}
    for r_cfg in retailers:
        advance_results[r_cfg.get("name", "retailer")] = advance_app(
            r_cfg["url"], r_cfg.get("name", "retailer")
        )

    advance_results[mfr_name] = advance_app(mfr["url"], mfr_name)

    for p_cfg in providers:
        advance_results[p_cfg.get("name", "provider")] = advance_app(
            p_cfg["url"], p_cfg.get("name", "provider")
        )

    summary["advance_results"] = advance_results
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

    for day in range(1, num_days + 1):
        run_day(config, scenario, day)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
