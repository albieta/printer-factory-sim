from __future__ import annotations

from datetime import date
from typing import Any

STARTER_CONFIG: dict[str, Any] = {
    "warehouse_capacity": 2200,
    "assembly_lines": 1,
    "workers_per_line": 1,
    "shift_hours": 8.0,
    "daily_assembly_hours": 8.0,
    "demand_distribution_mean": 5.0,
    "demand_distribution_variance": 2.0,
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

STARTER_SUPPLIERS: list[dict[str, Any]] = [
    {
        "name": "FilamentPro Inc.",
        "product": "PLA Filament",
        "unit_cost": 25.00,
        "lead_time_days": 5,
        "quantity_breaks": [{"qty": 100, "price": 22.50}, {"qty": 500, "price": 20.00}],
    },
    {
        "name": "ABS Materials Ltd.",
        "product": "ABS Filament",
        "unit_cost": 30.00,
        "lead_time_days": 7,
        "quantity_breaks": [{"qty": 150, "price": 27.00}, {"qty": 600, "price": 24.00}],
    },
    {
        "name": "MetalWorks Supply",
        "product": "Aluminum Frame",
        "unit_cost": 45.00,
        "lead_time_days": 10,
        "quantity_breaks": [{"qty": 50, "price": 42.00}, {"qty": 200, "price": 38.00}],
    },
    {
        "name": "MotorTech Direct",
        "product": "Stepper Motor",
        "unit_cost": 15.00,
        "lead_time_days": 14,
        "quantity_breaks": [{"qty": 100, "price": 13.50}, {"qty": 400, "price": 12.00}],
    },
    {
        "name": "ElectroComponents",
        "product": "Control Board",
        "unit_cost": 35.00,
        "lead_time_days": 12,
        "quantity_breaks": [{"qty": 75, "price": 32.00}, {"qty": 300, "price": 28.00}],
    },
    {
        "name": "DisplayTech Solutions",
        "product": "LCD Screen",
        "unit_cost": 50.00,
        "lead_time_days": 15,
        "quantity_breaks": [{"qty": 50, "price": 47.00}, {"qty": 250, "price": 43.00}],
    },
]

STARTER_INVENTORY: dict[str, float] = {
    "PLA Filament": 500.0,
    "ABS Filament": 400.0,
    "Aluminum Frame": 200.0,
    "Stepper Motor": 300.0,
    "Control Board": 150.0,
    "LCD Screen": 100.0,
}

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
