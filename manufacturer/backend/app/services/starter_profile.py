from __future__ import annotations

from datetime import date
from typing import Any

STARTER_CONFIG: dict[str, Any] = {
    "warehouse_capacity": 8400,
    "assembly_lines": 1,
    "workers_per_line": 1,
    "shift_hours": 8.0,
    "daily_assembly_hours": 8.0,
    "demand_distribution_mean": 5.0,
    "demand_distribution_variance": 2.0,
    "internal_demand_enabled": False,
    "sim_day": 0,
    "cost_per_assembly_line": 50000.0,
    "cost_per_assembly_line_per_day": 100.0,
    "cost_per_worker_per_hour": 50.0,
    "max_workers_per_line": 10,
    "total_costs": 0.0,
    "total_revenue": 0.0,
}

STARTER_PRINTERS: list[dict[str, Any]] = [
    {"name": "Basic300", "assembly_hours": 2.0},
    {"name": "Pro450", "assembly_hours": 4.0},
    {"name": "Elite700", "assembly_hours": 6.0},
]

STARTER_MATERIALS: list[str] = [
    "PLA Filament",
    "ABS Filament",
    "Aluminum Frame",
    "Stepper Motor",
    "Control Board",
    "LCD Screen",
]

STARTER_BOM: dict[str, list[dict[str, Any]]] = {
    "Basic300": [
        {"material": "PLA Filament", "quantity": 2.5},
        {"material": "Aluminum Frame", "quantity": 1.0},
        {"material": "Stepper Motor", "quantity": 3.0},
        {"material": "Control Board", "quantity": 1.0},
    ],
    "Pro450": [
        {"material": "ABS Filament", "quantity": 4.0},
        {"material": "Aluminum Frame", "quantity": 2.0},
        {"material": "Stepper Motor", "quantity": 4.0},
        {"material": "Control Board", "quantity": 2.0},
    ],
    "Elite700": [
        {"material": "ABS Filament", "quantity": 6.0},
        {"material": "Aluminum Frame", "quantity": 3.0},
        {"material": "Stepper Motor", "quantity": 6.0},
        {"material": "Control Board", "quantity": 2.0},
        {"material": "LCD Screen", "quantity": 1.0},
    ],
}

STARTER_INVENTORY: dict[str, float] = {
    "PLA Filament": 500.0,
    "ABS Filament": 400.0,
    "Aluminum Frame": 200.0,
    "Stepper Motor": 600.0,
    "Control Board": 150.0,
    "LCD Screen": 100.0,
}

STARTER_SUPPLIERS: list[dict[str, Any]] = [
    {
        "name": "PlasticWorks Inc",
        "product": "PLA Filament",
        "unit_cost": 15.0,
        "lead_time_days": 1,
        "quantity_breaks": [{"qty": 100, "price": 15.0}, {"qty": 500, "price": 14.25}, {"qty": 1000, "price": 13.5}],
    },
    {
        "name": "PolymerSupply Co",
        "product": "ABS Filament",
        "unit_cost": 18.0,
        "lead_time_days": 1,
        "quantity_breaks": [{"qty": 100, "price": 18.0}, {"qty": 500, "price": 17.1}, {"qty": 1000, "price": 16.2}],
    },
    {
        "name": "MetalSource Ltd",
        "product": "Aluminum Frame",
        "unit_cost": 25.0,
        "lead_time_days": 2,
        "quantity_breaks": [{"qty": 50, "price": 25.0}, {"qty": 200, "price": 23.75}, {"qty": 500, "price": 22.5}],
    },
    {
        "name": "MotorTech USA",
        "product": "Stepper Motor",
        "unit_cost": 12.0,
        "lead_time_days": 1,
        "quantity_breaks": [{"qty": 100, "price": 12.0}, {"qty": 500, "price": 11.4}, {"qty": 1000, "price": 10.8}],
    },
    {
        "name": "ChipSupply Co",
        "product": "Control Board",
        "unit_cost": 45.0,
        "lead_time_days": 3,
        "quantity_breaks": [{"qty": 50, "price": 45.0}, {"qty": 100, "price": 42.75}, {"qty": 250, "price": 40.5}],
    },
    {
        "name": "DisplayTech Inc",
        "product": "LCD Screen",
        "unit_cost": 60.0,
        "lead_time_days": 2,
        "quantity_breaks": [{"qty": 25, "price": 60.0}, {"qty": 50, "price": 57.0}, {"qty": 100, "price": 54.0}],
    },
]

ORDER_STATUS_LABELS = {
    "PENDING": "Awaiting Release",
    "RELEASED": "Queued for Production",
    "COMPLETED": "Completed",
    "BLOCKED": "Blocked by Material Shortage",
    "REJECTED": "Rejected",
}

PURCHASE_ORDER_STATUS_LABELS = {
    "PENDING": "In Transit",
    "DELIVERED": "Received",
    "REJECTED": "Rejected",
}

WORKFLOW_STAGE_DEFS: list[dict[str, str]] = [
    {
        "key": "demand",
        "label": "Demand Arrives",
        "route": "/",
        "description": "New manufacturing demand enters the system each simulation day.",
    },
    {
        "key": "release",
        "label": "Orders Reviewed",
        "route": "/orders",
        "description": "Pending orders are checked for material availability before release.",
    },
    {
        "key": "assembly",
        "label": "Assembly Runs",
        "route": "/production",
        "description": "Released orders consume shared daily assembly capacity and raw materials.",
    },
    {
        "key": "procurement",
        "label": "Procurement Replenishes",
        "route": "/suppliers",
        "description": "Purchase orders travel through supplier lead times until delivery day.",
    },
    {
        "key": "storage",
        "label": "Inventory & Storage",
        "route": "/inventory",
        "description": "Inbound deliveries and production drawdowns change warehouse pressure.",
    },
    {
        "key": "outcomes",
        "label": "Outcomes Explained",
        "route": "/reports",
        "description": "Events, completions, and bottlenecks are summarized for analysis.",
    },
]


def calculate_effective_daily_assembly_hours(
    assembly_lines: int,
    workers_per_line: int,
    shift_hours: float,
) -> float:
    return float(assembly_lines * workers_per_line * shift_hours)



def build_starter_config(sim_date: date | None = None) -> dict[str, Any]:
    config = dict(STARTER_CONFIG)
    config["sim_date"] = sim_date or date.today()
    config["daily_assembly_hours"] = calculate_effective_daily_assembly_hours(
        config["assembly_lines"],
        config["workers_per_line"],
        config["shift_hours"],
    )
    return config
