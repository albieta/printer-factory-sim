"""Generate Week 8 charts and a written run interpretation.

Usage:

    python -m engine.analyze_run logs/metrics.jsonl \
      --scenario scenarios/holiday-rush.json \
      --out analysis/holiday-rush
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any


PRINTER_MODELS = {"Basic300", "Pro450", "Elite700"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_metrics(path: Path, scenario_name: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if scenario_name is not None and row.get("scenario") != scenario_name:
                continue
            rows.append(row)
    return sorted(rows, key=lambda row: int(row.get("day", 0)))


def _plt() -> Any:
    import matplotlib  # type: ignore[import-not-found]

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore[import-not-found]

    return plt


def _sum_values(values: dict[str, Any]) -> float:
    total = 0.0
    for value in values.values():
        try:
            total += float(value)
        except (TypeError, ValueError):
            continue
    return total


def _manufacturer_inventory(row: dict[str, Any]) -> dict[str, float]:
    manufacturer = row.get("manufacturer", {})
    if not isinstance(manufacturer, dict):
        return {}
    inventory = manufacturer.get("inventory", {})
    return inventory if isinstance(inventory, dict) else {}


def _retailer_stock(row: dict[str, Any]) -> dict[str, float]:
    stock: dict[str, float] = {}
    for retailer in row.get("retailers", []):
        if not isinstance(retailer, dict):
            continue
        items = retailer.get("stock", {})
        if not isinstance(items, dict):
            continue
        for model, qty in items.items():
            stock[str(model)] = stock.get(str(model), 0.0) + float(qty)
    return stock


def _provider_prices(row: dict[str, Any]) -> dict[str, dict[str, float]]:
    providers = row.get("providers", [])
    if not providers or not isinstance(providers[0], dict):
        return {}
    prices = providers[0].get("prices", {})
    return prices if isinstance(prices, dict) else {}


def _manufacturer_prices(row: dict[str, Any]) -> dict[str, float]:
    manufacturer = row.get("manufacturer", {})
    if not isinstance(manufacturer, dict):
        return {}
    prices = manufacturer.get("prices", {})
    return prices if isinstance(prices, dict) else {}


def _retailer_prices(row: dict[str, Any]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for retailer in row.get("retailers", []):
        if not isinstance(retailer, dict):
            continue
        entries = retailer.get("prices", {})
        if isinstance(entries, dict):
            prices.update({str(model): float(price) for model, price in entries.items()})
    return prices


def _customer_counts(row: dict[str, Any]) -> tuple[int, int, int]:
    placed = fulfilled = backordered = 0
    for retailer in row.get("retailers", []):
        if not isinstance(retailer, dict):
            continue
        orders = retailer.get("customer_orders", {})
        if not isinstance(orders, dict):
            continue
        placed += int(orders.get("placed_today", 0))
        fulfilled += int(orders.get("fulfilled_today", 0))
        backordered += int(orders.get("backordered_today", 0))
    return placed, fulfilled, backordered


def _plot_inventory(rows: list[dict[str, Any]], out_dir: Path) -> None:
    plt = _plt()
    days = [int(row["day"]) for row in rows]
    mfr_parts: list[float] = []
    mfr_finished: list[float] = []
    retailer_printers: list[float] = []

    for row in rows:
        mfr_inventory = _manufacturer_inventory(row)
        mfr_finished.append(
            sum(float(qty) for name, qty in mfr_inventory.items() if name in PRINTER_MODELS)
        )
        mfr_parts.append(
            sum(float(qty) for name, qty in mfr_inventory.items() if name not in PRINTER_MODELS)
        )
        retailer_printers.append(_sum_values(_retailer_stock(row)))

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(days, mfr_parts, marker="o", label="Manufacturer parts")
    ax.plot(days, mfr_finished, marker="o", label="Manufacturer finished printers")
    ax.plot(days, retailer_printers, marker="o", label="Retailer printers")
    ax.set_title("Inventory Over Time")
    ax.set_xlabel("Simulated day")
    ax.set_ylabel("Units")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "inventory_over_time.png", dpi=160)
    plt.close(fig)


def _plot_prices(rows: list[dict[str, Any]], out_dir: Path) -> None:
    plt = _plt()
    days = [int(row["day"]) for row in rows]

    provider_control_board = []
    manufacturer_basic = []
    retailer_basic = []
    for row in rows:
        provider_control_board.append(
            _provider_prices(row).get("Control Board", {}).get("1", math.nan)
        )
        manufacturer_basic.append(_manufacturer_prices(row).get("Basic300", math.nan))
        retailer_basic.append(_retailer_prices(row).get("Basic300", math.nan))

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(days, provider_control_board, marker="o", label="Provider Control Board tier 1")
    ax.plot(days, manufacturer_basic, marker="o", label="Manufacturer Basic300 wholesale")
    ax.plot(days, retailer_basic, marker="o", label="Retailer Basic300 retail")
    ax.set_title("Representative Prices Over Time")
    ax.set_xlabel("Simulated day")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "prices_over_time.png", dpi=160)
    plt.close(fig)


def _plot_fulfillment(rows: list[dict[str, Any]], out_dir: Path) -> None:
    plt = _plt()
    days = [int(row["day"]) for row in rows]
    placed: list[int] = []
    fulfilled: list[int] = []
    backordered: list[int] = []
    for row in rows:
        p, f, b = _customer_counts(row)
        placed.append(p)
        fulfilled.append(f)
        backordered.append(b)

    x = list(range(len(days)))
    width = 0.27
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar([i - width for i in x], placed, width=width, label="Placed")
    ax.bar(x, fulfilled, width=width, label="Fulfilled")
    ax.bar([i + width for i in x], backordered, width=width, label="Backordered")
    ax.set_title("Daily Customer Order Fulfillment")
    ax.set_xlabel("Simulated day")
    ax.set_ylabel("Orders")
    ax.set_xticks(x)
    ax.set_xticklabels([str(day) for day in days])
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "order_fulfillment.png", dpi=160)
    plt.close(fig)


def _plot_events(scenario: dict[str, Any], rows: list[dict[str, Any]], out_dir: Path) -> None:
    plt = _plt()
    events = [event for event in scenario.get("events", []) if isinstance(event, dict)]
    fig, ax = plt.subplots(figsize=(10, max(2.5, len(events) * 0.55)))

    for index, event in enumerate(events):
        start = int(event.get("start_day", 1))
        end = int(event.get("end_day", start))
        ax.broken_barh([(start, end - start + 1)], (index - 0.35, 0.7))
        ax.text(start, index, str(event.get("name", "event")), va="center", ha="left")

    if rows:
        min_day = min(int(row["day"]) for row in rows)
        max_day = max(int(row["day"]) for row in rows)
        ax.set_xlim(min_day, max_day + 1)
    ax.set_ylim(-1, max(1, len(events)))
    ax.set_yticks([])
    ax.set_title("Scenario Event Overlay")
    ax.set_xlabel("Simulated day")
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "event_overlay.png", dpi=160)
    plt.close(fig)


def _price_direction_changes(values: list[float]) -> int:
    directions: list[int] = []
    previous: float | None = None
    for value in values:
        if math.isnan(value):
            continue
        if previous is None:
            previous = value
            continue
        if value > previous:
            directions.append(1)
        elif value < previous:
            directions.append(-1)
        previous = value
    return sum(1 for idx in range(1, len(directions)) if directions[idx] != directions[idx - 1])


def _write_interpretation(
    rows: list[dict[str, Any]],
    scenario: dict[str, Any],
    out_dir: Path,
    comparison_text: str | None,
) -> None:
    if not rows:
        (out_dir / "interpretation.md").write_text("No metrics rows found.\n", encoding="utf-8")
        return

    days = [int(row["day"]) for row in rows]
    placed = []
    fulfilled = []
    backordered = []
    retailer_stock = []
    mfr_parts = []
    retail_prices = []

    for row in rows:
        p, f, b = _customer_counts(row)
        placed.append(p)
        fulfilled.append(f)
        backordered.append(b)
        retailer_stock.append(_sum_values(_retailer_stock(row)))
        mfr_inventory = _manufacturer_inventory(row)
        mfr_parts.append(
            sum(float(qty) for name, qty in mfr_inventory.items() if name not in PRINTER_MODELS)
        )
        retail_prices.append(_retailer_prices(row).get("Basic300", math.nan))

    stockout_days = [day for day, count in zip(days, backordered) if count > 0]
    fulfillment_rates = [
        fulfilled_count / placed_count
        for placed_count, fulfilled_count in zip(placed, fulfilled)
        if placed_count > 0
    ]
    avg_rate = mean(fulfillment_rates) if fulfillment_rates else 0.0

    black_friday_row = next(
        (
            row
            for row in rows
            if "black_friday" in row.get("signal", {}).get("active_events", [])
        ),
        None,
    )
    black_friday_note = "No Black Friday event was active in this run."
    if black_friday_row is not None:
        day = black_friday_row.get("day")
        stock = _sum_values(_retailer_stock(black_friday_row))
        black_friday_note = (
            f"Black Friday first appeared on day {day}; retailer stock at that snapshot "
            f"was {stock:.0f} printers."
        )

    oscillations = _price_direction_changes(retail_prices)
    stockout_note = (
        f"Stockouts/backorders first appeared on day {stockout_days[0]}."
        if stockout_days
        else "No customer backorders were captured in the metrics snapshots."
    )
    bullwhip_note = (
        "Provider and manufacturer order quantities should be checked in the agent logs "
        "for a true bullwhip claim; this automated report flags the days where demand "
        "and backorders diverged most."
    )

    text = [
        f"# Analysis: {scenario.get('scenario_name', rows[0].get('scenario', 'run'))}",
        "",
        "## Inventory",
        (
            f"Manufacturer parts moved from {mfr_parts[0]:.0f} to {mfr_parts[-1]:.0f} units, "
            f"while retailer printer stock moved from {retailer_stock[0]:.0f} to "
            f"{retailer_stock[-1]:.0f}. Read this next to the event overlay: sharp drops "
            "usually correspond to demand shocks or delayed replenishment."
        ),
        "",
        "## Prices",
        (
            f"Basic300 retail price changed direction {oscillations} time(s). "
            "A low count suggests stabilizing behavior; repeated direction changes suggest "
            "the retailer is reacting late or overcorrecting."
        ),
        "",
        "## Fulfillment",
        (
            f"Average same-day fulfillment rate across days with demand was {avg_rate:.1%}. "
            f"{stockout_note}"
        ),
        "",
        "## Required Questions",
        f"- Did the manufacturer build stock ahead of Black Friday? {black_friday_note}",
        f"- When stockouts happened, what was the proximate cause? {stockout_note} Inspect the matching day agent logs for the root cause.",
        f"- Did prices stabilize or oscillate? The Basic300 retail series changed direction {oscillations} time(s).",
        f"- Bullwhip moment: {bullwhip_note}",
    ]
    if comparison_text:
        text.extend(["", "## Scenario Comparison", comparison_text])

    (out_dir / "interpretation.md").write_text("\n".join(text) + "\n", encoding="utf-8")


def _comparison_text(
    baseline_rows: list[dict[str, Any]],
    current_rows: list[dict[str, Any]],
    baseline_label: str,
    current_label: str,
    out_dir: Path,
) -> str:
    plt = _plt()

    def series(rows: list[dict[str, Any]]) -> tuple[list[int], list[int], list[int]]:
        days: list[int] = []
        placed: list[int] = []
        backordered: list[int] = []
        for row in rows:
            p, _, b = _customer_counts(row)
            days.append(int(row["day"]))
            placed.append(p)
            backordered.append(b)
        return days, placed, backordered

    base_days, base_placed, base_backordered = series(baseline_rows)
    run_days, run_placed, run_backordered = series(current_rows)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(base_days, base_backordered, marker="o", label=f"{baseline_label} backordered")
    ax.plot(run_days, run_backordered, marker="o", label=f"{current_label} backordered")
    ax.plot(base_days, base_placed, linestyle="--", alpha=0.6, label=f"{baseline_label} placed")
    ax.plot(run_days, run_placed, linestyle="--", alpha=0.6, label=f"{current_label} placed")
    ax.set_title("Scenario Comparison: Demand and Backorders")
    ax.set_xlabel("Simulated day")
    ax.set_ylabel("Orders")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "scenario_comparison.png", dpi=160)
    plt.close(fig)

    base_backorders = sum(base_backordered)
    run_backorders = sum(run_backordered)
    return (
        f"{current_label} produced {run_backorders} captured same-day backorders versus "
        f"{base_backorders} in {baseline_label}. Compare this with the placed-order lines: "
        "a successful volatile run should show larger, earlier upstream responses without "
        "letting backorders grow unchecked."
    )


def analyze(
    metrics_path: Path,
    scenario_path: Path,
    out_dir: Path,
    baseline_metrics_path: Path | None,
    baseline_label: str,
    run_label: str | None,
) -> None:
    scenario = _load_json(scenario_path)
    scenario_name = str(scenario.get("scenario_name", ""))
    rows = _load_metrics(metrics_path, scenario_name=scenario_name or None)
    if not rows:
        rows = _load_metrics(metrics_path)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.jsonl").write_text(
        "".join(json.dumps(row, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )

    _plot_inventory(rows, out_dir)
    _plot_prices(rows, out_dir)
    _plot_fulfillment(rows, out_dir)
    _plot_events(scenario, rows, out_dir)

    comparison = None
    if baseline_metrics_path is not None:
        baseline_rows = _load_metrics(baseline_metrics_path)
        comparison = _comparison_text(
            baseline_rows,
            rows,
            baseline_label,
            run_label or scenario_name or "current",
            out_dir,
        )

    _write_interpretation(rows, scenario, out_dir, comparison)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Week 8 simulation charts.")
    parser.add_argument("metrics", type=Path, help="Path to metrics.jsonl from the run")
    parser.add_argument("--scenario", type=Path, required=True, help="Scenario JSON for event overlay")
    parser.add_argument("--out", type=Path, required=True, help="Output directory for charts/report")
    parser.add_argument("--baseline-metrics", type=Path, default=None, help="Optional baseline metrics for comparison")
    parser.add_argument("--baseline-label", default="baseline", help="Label for baseline metrics")
    parser.add_argument("--run-label", default=None, help="Label for this run in comparison output")
    args = parser.parse_args(argv)

    analyze(
        metrics_path=args.metrics,
        scenario_path=args.scenario,
        out_dir=args.out,
        baseline_metrics_path=args.baseline_metrics,
        baseline_label=args.baseline_label,
        run_label=args.run_label,
    )
    print(f"Wrote analysis to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
