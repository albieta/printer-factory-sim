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
    """Return a list of (model_name, quantity) customer order tuples.

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
        # Demand falls as retail price exceeds the base; steeper curve makes consumers more price-sensitive.
        # Formula: elasticity = max(0.05, (1.0 - (price - bp) / bp) ^ 1.3)
        # This creates a J-curve: small price increases reduce demand moderately,
        # large increases cause demand collapse. Floor of 0.05 means even extreme prices
        # maintain only 5% of baseline (not 20%), making high prices more punishing.
        if bp > 0:
            linear_factor = max(0.0, 1.0 - (price - bp) / bp)  # Clamp to 0 so we don't get complex numbers
            price_factor = max(0.05, linear_factor ** 1.3)  # Power of 1.3 steepens the curve
        else:
            price_factor = 1.0
        n = max(0, int(random.gauss(mean_orders * price_factor, variance**0.5)))
        for _ in range(n):
            qty = random.choices([1, 2, 3], weights=[85, 12, 3])[0]
            orders.append((model, qty))

    return orders


def _as_float(value: Any, default: float) -> float:
    """Best-effort float coercion for scenario modifier values."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_day_signal(scenario: dict[str, Any], day: int) -> dict[str, Any]:
    """Return the market signal that applies to *day*.

    Week 8 scenarios can have overlapping events. Numeric modifiers compound by
    multiplication, so a chip shortage and holiday rush can both pressure the
    same day. Non-numeric hints, such as ``price_sensitivity``, use the last
    active event that sets them.
    """

    base_demand = scenario.get("base_demand", {"mean": 5, "variance": 2})

    active_events: list[dict[str, Any]] = []
    for event in scenario.get("events", []):
        if event.get("start_day", 0) <= day <= event.get("end_day", 9999):
            active_events.append(event)

    signal: dict[str, Any] = {
        "base_demand": base_demand,
        "demand_modifier": 1.0,
        "supply_modifier": 1.0,
        "lead_time_modifier": 1.0,
        "active_events": [],
        "compounding": "multiply",
    }

    if not active_events:
        return signal

    for event in active_events:
        if "base_demand" in event:
            signal["base_demand"] = event["base_demand"]
        for key in ("demand_modifier", "supply_modifier", "lead_time_modifier"):
            signal[key] = float(signal[key]) * _as_float(event.get(key), 1.0)
        if "price_sensitivity" in event:
            signal["price_sensitivity"] = event["price_sensitivity"]

    signal["active_events"] = [str(event.get("name", "unnamed")) for event in active_events]
    signal["event_descriptions"] = {
        str(event.get("name", "unnamed")): str(event.get("description", ""))
        for event in active_events
        if event.get("description")
    }
    return signal
