"""Entry point: python -m engine"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False, help="Turn engine — orchestrates all three supply-chain apps.")


@app.command()
def main(
    scenario: Path = typer.Option(
        Path("engine/scenarios/week7-default.json"),
        "--scenario",
        help="Path to scenario JSON file.",
        exists=True,
        readable=True,
    ),
    days: Optional[int] = typer.Option(
        None,
        "--days",
        help="Number of days to simulate (default: use scenario days count).",
    ),
    seed: int = typer.Option(42, "--seed", help="RNG seed for demand generation."),
    log_dir: Path = typer.Option(
        Path("logs"),
        "--log-dir",
        help="Directory for KPI CSV and agent logs.",
    ),
    agent: list[str] = typer.Option(
        [],
        "--agent",
        help="Agent override in role=mode format, e.g. manufacturer=llm. Repeatable.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable DEBUG logging."),
) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from typing import Any
    scenario_data: dict[str, Any] = json.loads(scenario.read_text())

    # Resolve number of turns
    day_configs: list[dict[str, Any]] = scenario_data.get("days", [])
    n_days = days if days is not None else len(day_configs)
    if n_days <= 0:
        typer.echo("No days to simulate.", err=True)
        raise typer.Exit(1)

    # Parse agent overrides: "manufacturer=llm" → {"manufacturer": "llm"}
    agent_overrides: dict[str, str] = {}
    for spec in agent:
        if "=" not in spec:
            typer.echo(f"Invalid --agent format '{spec}' (expected role=mode).", err=True)
            raise typer.Exit(1)
        role, mode = spec.split("=", 1)
        agent_overrides[role.strip()] = mode.strip()

    from engine.agents import build_agents
    from engine.runner import run

    retailer_agent, manufacturer_agent, provider_agent = build_agents(
        scenario_data, agent_overrides, log_dir=log_dir
    )

    typer.echo(f"Starting turn engine: scenario={scenario} days={n_days} seed={seed}")
    run(
        scenario=scenario_data,
        days=n_days,
        seed=seed,
        log_dir=log_dir,
        retailer_agent=retailer_agent,
        manufacturer_agent=manufacturer_agent,
        provider_agent=provider_agent,
    )
    typer.echo(f"Done. KPI log: {log_dir / 'kpi.csv'}")


if __name__ == "__main__":
    app()
