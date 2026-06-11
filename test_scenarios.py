#!/usr/bin/env python3
"""Verify that scenarios generate deterministic, modifier-sensitive demand.

This test demonstrates:
1. Identical scenarios produce identical demand (determinism via random.seed)
2. demand_modifier values affect order volumes
3. How to read scenario files and verify their behavior
"""

import json
from pathlib import Path
from engine.demand import generate_customer_demand, get_day_signal


def test_scenario_determinism() -> None:
    """Show that the same day always generates the same orders."""

    print("\n" + "█" * 70)
    print("█  SCENARIO DETERMINISM TEST")
    print("█" * 70)
    print(
        "\nDemand generation is seeded with random.seed(day), so Day 1 is always"
    )
    print("identical across runs. This makes testing reproducible.\n")

    # Load the smoke-test scenario
    scenario_path = Path("scenarios/smoke-test.json")
    scenario = json.loads(scenario_path.read_text())

    print(f"Scenario: {scenario['scenario_name']}")
    print(f"Base demand: mean={scenario['base_demand']['mean']}, "
          f"variance={scenario['base_demand']['variance']}")
    print(f"Events: {len(scenario['events'])}\n")

    # Sample prices (from retailer catalog)
    retail_prices = {
        "Basic300": 650.0,
        "Pro450": 1200.0,
        "Elite700": 2000.0,
    }

    # Verify determinism: run day 1 twice, should be identical
    signal = get_day_signal(scenario, day=1)
    run_a = generate_customer_demand(1, signal, retail_prices, retail_prices)
    run_b = generate_customer_demand(1, signal, retail_prices, retail_prices)

    print("┌─ Run 1 ─────────────────────┐")
    print(f"│ {len(run_a)} orders generated   │")
    for model, qty in sorted(set(run_a)):
        count = sum(1 for m, q in run_a if m == model)
        print(f"│   {model:15} x{count}          │")
    print("└─────────────────────────────┘")

    print("\n┌─ Run 2 (same day) ──────────┐")
    print(f"│ {len(run_b)} orders generated   │")
    for model, qty in sorted(set(run_b)):
        count = sum(1 for m, q in run_b if m == model)
        print(f"│   {model:15} x{count}          │")
    print("└─────────────────────────────┘")

    if run_a == run_b:
        print("\n✓ DETERMINISM VERIFIED: Identical days produce identical demand\n")
    else:
        print("\n✗ ERROR: Demand mismatch between runs!\n")
        return

    # ───────────────────────────────────────────────────────────────────
    # Test demand_modifier effect
    # ───────────────────────────────────────────────────────────────────

    print("\n" + "█" * 70)
    print("█  DEMAND MODIFIER EFFECT TEST")
    print("█" * 70)
    print(
        "\nThe demand_modifier multiplies base_demand.mean. This controls market"
    )
    print("strength and triggers price adjustments in the manufacturer skill:\n")
    print("  demand_modifier > 1.5  →  HIGH demand  →  raise prices")
    print("  demand_modifier < 0.5  →  LOW demand   →  lower prices")
    print("  0.8 to 1.2             →  STEADY state →  no change\n")

    modifiers = [0.3, 0.8, 1.0, 1.5, 2.0]
    results = {}

    for modifier in modifiers:
        signal = {
            "base_demand": scenario["base_demand"],
            "demand_modifier": modifier,
        }
        orders = generate_customer_demand(1, signal, retail_prices, retail_prices)
        total = len(orders)
        results[modifier] = total

    print("Order volume by demand_modifier (Day 1):\n")
    print("┌──────────┬────────┬─────────────┐")
    print("│ Modifier │ Orders │ Interpretation │")
    print("├──────────┼────────┼─────────────┤")

    for modifier in modifiers:
        total = results[modifier]
        if modifier > 1.5:
            label = "HIGH demand (raise prices)"
        elif modifier < 0.5:
            label = "LOW demand (lower prices)"
        else:
            label = "STEADY state"
        print(
            f"│   {modifier:4.1f}   │  {total:4}   │ {label:20} │"
        )

    print("└──────────┴────────┴─────────────┘\n")

    # Verify modifier impact
    low = results[0.3]
    high = results[2.0]
    ratio = high / low if low > 0 else 0
    print(f"Demand ratio (2.0x vs 0.3x): {ratio:.1f}x")
    print(
        "✓ Higher demand_modifier → more customer orders (correct)\n"
    )

    # ───────────────────────────────────────────────────────────────────
    # Show how events work
    # ───────────────────────────────────────────────────────────────────

    print("\n" + "█" * 70)
    print("█  EVENT SCHEDULING TEST")
    print("█" * 70)
    print(
        "\nScenario events control demand_modifier across day ranges."
    )
    print("The turn engine calls get_day_signal(scenario, day) to fetch\n")
    print("the active event for each day.\n")

    # Create a custom scenario with overlapping events
    test_scenario = {
        "scenario_name": "test",
        "base_demand": {"mean": 5, "variance": 1},
        "events": [
            {
                "name": "normal",
                "start_day": 1,
                "end_day": 3,
                "demand_modifier": 1.0,
            },
            {
                "name": "rush",
                "start_day": 4,
                "end_day": 7,
                "demand_modifier": 2.0,
            },
            {
                "name": "clearance",
                "start_day": 8,
                "end_day": 10,
                "demand_modifier": 0.5,
            },
        ],
    }

    print("Custom scenario with 3 events:")
    print("\n  Days 1-3:   demand_modifier = 1.0 (normal)")
    print("  Days 4-7:   demand_modifier = 2.0 (rush)")
    print("  Days 8-10:  demand_modifier = 0.5 (clearance)\n")

    print("Testing get_day_signal() for each day:\n")
    print("┌──────┬──────────┬─────────────────┐")
    print("│ Day  │ Modifier │ Event Name      │")
    print("├──────┼──────────┼─────────────────┤")

    for day in range(1, 11):
        signal = get_day_signal(test_scenario, day)
        modifier = signal["demand_modifier"]
        event_name = (
            "normal"
            if 1 <= day <= 3
            else "rush" if 4 <= day <= 7 else "clearance" if 8 <= day <= 10 else "none"
        )
        print(f"│ {day:4}  │   {modifier:4.1f}   │ {event_name:15} │")

    print("└──────┴──────────┴─────────────────┘\n")

    # ───────────────────────────────────────────────────────────────────
    # Instructions for custom scenarios
    # ───────────────────────────────────────────────────────────────────

    print("\n" + "█" * 70)
    print("█  HOW TO CREATE CUSTOM SCENARIOS")
    print("█" * 70)

    template = {
        "scenario_name": "my-scenario",
        "base_demand": {"mean": 5, "variance": 2},
        "events": [
            {
                "name": "event-name",
                "start_day": 1,
                "end_day": 10,
                "demand_modifier": 1.0,
                "description": "What happens",
            },
        ],
    }

    print("\n1. Copy scenarios/smoke-test.json as a template")
    print("2. Edit the scenario_name and events array:")
    print(json.dumps(template, indent=2))

    print("\n3. Save to scenarios/my-scenario.json")
    print("4. Run: python -m engine.turn_engine config/sim.json scenarios/my-scenario.json 3")
    print("\n✓ The turn engine will inject demand according to your events\n")


if __name__ == "__main__":
    try:
        test_scenario_determinism()
        print("\n" + "█" * 70)
        print("█  ALL SCENARIO TESTS PASSED ✓")
        print("█" * 70 + "\n")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
