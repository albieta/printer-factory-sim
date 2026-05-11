"""Main turn loop for the turn engine."""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any

import httpx

from engine.agents import LLMManufacturerAgent, ManufacturerAgent, ProviderAgent, RetailerAgent
from engine.demand import generate_customer_demand
from engine.kpi import append_kpi_row, collect_kpis

logger = logging.getLogger(__name__)


def run(
    scenario: dict[str, Any],
    days: int,
    seed: int,
    log_dir: Path,
    retailer_agent: RetailerAgent,
    manufacturer_agent: ManufacturerAgent | LLMManufacturerAgent,
    provider_agent: ProviderAgent,
) -> None:
    apps = scenario.get("apps", {})
    retailer_url: str = apps.get("retailer", {}).get("url", "http://localhost:8003")
    manufacturer_url: str = apps.get("manufacturer", {}).get("url", "http://localhost:8002")
    provider_url: str = apps.get("provider", {}).get("url", "http://localhost:8001")

    base_price: float = float(scenario.get("base_price", 999))
    day_configs: list[dict[str, Any]] = scenario.get("days", [])

    rng = random.Random(seed)

    for turn in range(1, days + 1):
        signal = _signal_for_day(turn, day_configs)
        logger.info("=== Day %d | signal=%s ===", turn, signal)

        # 1. Fetch retailer catalog prices for demand generation
        retailer_prices = _get_retailer_prices(retailer_url)
        if not retailer_prices:
            logger.warning("Day %d: no retailer prices — skipping demand generation", turn)
        else:
            # 2. Generate customer demand and post individual orders
            demand = generate_customer_demand(turn, signal, retailer_prices, base_price, rng)
            logger.info("Day %d: generated %d customer orders", turn, len(demand))
            _post_customer_orders(retailer_url, demand)

        # 3. Run agents (retailer restocks, manufacturer procures, provider is passive)
        retailer_agent.run(turn, signal)
        manufacturer_agent.run(turn, signal)
        provider_agent.run(turn, signal)

        # 4. Advance days downstream-first: retailer → manufacturer → provider
        _advance_day(retailer_url, "retailer")
        _advance_day(manufacturer_url, "manufacturer")
        _advance_day(provider_url, "provider")

        # 5. Collect and write KPIs
        kpi_row = collect_kpis(turn, signal, retailer_url, manufacturer_url, provider_url)
        append_kpi_row(log_dir, kpi_row)
        logger.info("Day %d KPIs: %s", turn, kpi_row)


def _signal_for_day(day: int, day_configs: list[dict[str, Any]]) -> dict[str, Any]:
    for cfg in day_configs:
        if cfg.get("day") == day:
            return cfg
    return {"day": day}


def _get_retailer_prices(retailer_url: str) -> dict[str, float]:
    base = retailer_url.rstrip("/")
    try:
        resp = httpx.get(f"{base}/api/catalog", timeout=5.0)
        resp.raise_for_status()
        catalog: list[dict[str, Any]] = resp.json()
        return {item["model_name"]: float(item["retail_price"]) for item in catalog}
    except (httpx.HTTPError, KeyError) as exc:
        logger.warning("Could not fetch retailer catalog: %s", exc)
        return {}


def _post_customer_orders(retailer_url: str, demand: list[tuple[str, int]]) -> None:
    base = retailer_url.rstrip("/")
    with httpx.Client(timeout=10.0) as client:
        for model, qty in demand:
            try:
                resp = client.post(
                    f"{base}/api/orders",
                    json={"model": model, "quantity": qty, "customer_name": "Customer"},
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Failed to post customer order model=%s: %s", model, exc)


def _advance_day(base_url: str, role: str) -> None:
    base = base_url.rstrip("/")
    endpoints = {
        "retailer": f"{base}/api/day/advance",
        "manufacturer": f"{base}/api/simulation/advance-day",
        "provider": f"{base}/api/day/advance",
    }
    url = endpoints.get(role, f"{base}/api/day/advance")
    try:
        resp = httpx.post(url, timeout=15.0)
        resp.raise_for_status()
        logger.info("Advance %s: %s", role, resp.json())
    except httpx.HTTPError as exc:
        logger.error("Failed to advance day for %s: %s", role, exc)
