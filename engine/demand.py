"""Customer demand generator for the turn engine.

Implements PRD-week7 §6.4.  A turn is seeded with `random.seed(day)` so
every run is reproducible; Week 8 will toggle this off for stochastic runs.

Usage::

    signal = {"base_demand": {"mean": 4, "variance": 1}, "demand_modifier": 1.0}
    base_prices = {"Basic300": 650.0, "Pro450": 1200.0, "Elite700": 2000.0}
    retail_prices = {"Basic300": 660.0, "Pro450": 1250.0, "Elite700": 2100.0}
    orders = generate_customer_demand(1, signal, retail_prices, base_prices)
    # → list of (model_name, quantity) tuples
"""

from __future__ import annotations

import random
from typing import Any


def generate_customer_demand(
    day: int,
    signal: dict[str, Any],
    retail_prices: dict[str, float],
    base_prices: dict[str, float],
) -> list[tuple[str, int]]:
    """Return a list of (model_name, quantity=1) customer order tuples.

    Parameters
    ----------
    day:
        Current simulation day. Used to seed ``random`` for reproducibility.
    signal:
        Dict with keys ``base_demand`` (``{"mean": float, "variance": float}``)
        and ``demand_modifier`` (float).
    retail_prices:
        Current retail price for each model, keyed by model name.
    base_prices:
        Seeded retail price for each model (the "fair" price baseline).
    """

    random.seed(day)

    base = signal.get("base_demand", {"mean": 5, "variance": 2})
    modifier = float(signal.get("demand_modifier", 1.0))
    mean_orders = float(base.get("mean", 5)) * modifier
    variance = float(base.get("variance", 2))

    orders: list[tuple[str, int]] = []

    for model, price in retail_prices.items():
        bp = base_prices.get(model, price)
        # Demand falls as retail price exceeds the base; floor prevents collapse.
        price_factor = max(0.2, 1.0 - (price - bp) / bp) if bp > 0 else 1.0
        n = max(0, int(random.gauss(mean_orders * price_factor, variance**0.5)))
        orders.extend([(model, 1)] * n)

    return orders


def get_day_signal(scenario: dict[str, Any], day: int) -> dict[str, Any]:
    """Return the market signal that applies to *day*.

    Looks for the last ``events`` entry whose ``start_day <= day <= end_day``.
    Falls back to scenario-level ``base_demand`` with ``demand_modifier = 1.0``.
    """

    base_demand = scenario.get("base_demand", {"mean": 5, "variance": 2})

    active: dict[str, Any] | None = None
    for event in scenario.get("events", []):
        if event.get("start_day", 0) <= day <= event.get("end_day", 9999):
            active = event
            # Keep the last matching event (events are ordered chronologically).

    if active is None:
        return {"base_demand": base_demand, "demand_modifier": 1.0}

    return {
        "base_demand": active.get("base_demand", base_demand),
        "demand_modifier": float(active.get("demand_modifier", 1.0)),
    }
