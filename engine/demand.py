"""Customer demand generation for the turn engine."""

from __future__ import annotations

import random
from typing import Any


def generate_customer_demand(
    day: int,
    signal: dict[str, Any],
    retailer_prices: dict[str, float],
    base_price: float,
    rng: random.Random,
) -> list[tuple[str, int]]:
    """Return a list of (model_name, quantity=1) order tuples for a single day.

    Volume scales with demand_modifier and falls with price relative to base_price.
    Each tuple represents one unit so the caller posts them individually.
    """
    base: dict[str, Any] = signal.get("base_demand", {"mean": 5, "variance": 2})
    modifier: float = float(signal.get("demand_modifier", 1.0))
    orders: list[tuple[str, int]] = []

    for model, price in retailer_prices.items():
        mean_orders: float = float(base["mean"]) * modifier
        price_factor: float = max(0.2, 1.0 - (price - base_price) / base_price)
        adjusted_mean: float = mean_orders * price_factor
        n: int = max(0, int(rng.gauss(adjusted_mean, float(base["variance"]))))
        orders.extend([(model, 1)] * n)

    return orders
