from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.services.starter_profile import STARTER_INVENTORY, build_starter_config

DATABASE_URL = "sqlite:///./printer_factory_sim.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "manufacturing_orders": [
        ("reference_code", "ALTER TABLE manufacturing_orders ADD COLUMN reference_code VARCHAR(32)"),
        ("status_reason", "ALTER TABLE manufacturing_orders ADD COLUMN status_reason VARCHAR(255)"),
    ],
    "purchase_orders": [
        ("reference_code", "ALTER TABLE purchase_orders ADD COLUMN reference_code VARCHAR(32)"),
        ("status_reason", "ALTER TABLE purchase_orders ADD COLUMN status_reason VARCHAR(255)"),
    ],
    "simulation_config": [
        ("assembly_lines", "ALTER TABLE simulation_config ADD COLUMN assembly_lines INTEGER NOT NULL DEFAULT 1"),
        ("workers_per_line", "ALTER TABLE simulation_config ADD COLUMN workers_per_line INTEGER NOT NULL DEFAULT 1"),
        ("shift_hours", "ALTER TABLE simulation_config ADD COLUMN shift_hours FLOAT NOT NULL DEFAULT 8.0"),
    ],
}


def get_db_path() -> Path:
    return Path(__file__).resolve().parents[2] / "printer_factory_sim.db"


def column_exists(connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
    return any(row["name"] == column_name for row in rows)


def ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        for table_name, migrations in MIGRATIONS.items():
            for column_name, statement in migrations:
                if not column_exists(connection, table_name, column_name):
                    connection.execute(text(statement))

        starter_config = build_starter_config()
        starter_inventory_total = sum(STARTER_INVENTORY.values())
        connection.execute(
            text(
                """
                UPDATE simulation_config
                SET
                    assembly_lines = COALESCE(assembly_lines, 1),
                    workers_per_line = COALESCE(workers_per_line, 1),
                    shift_hours = COALESCE(shift_hours, daily_assembly_hours, :default_shift_hours),
                    daily_assembly_hours = (COALESCE(assembly_lines, 1) + COALESCE(workers_per_line, 1)) * COALESCE(shift_hours, daily_assembly_hours, :default_shift_hours),
                    warehouse_capacity = CASE
                        WHEN warehouse_capacity IS NULL THEN :default_capacity
                        WHEN warehouse_capacity = 1000 AND warehouse_capacity < (
                            SELECT COALESCE(SUM(quantity), 0)
                            FROM inventory
                        ) THEN :default_capacity
                        WHEN warehouse_capacity = 1000 AND :starter_inventory_total > warehouse_capacity THEN :default_capacity
                        ELSE warehouse_capacity
                    END,
                    demand_distribution_mean = COALESCE(demand_distribution_mean, :default_demand_mean),
                    demand_distribution_variance = COALESCE(demand_distribution_variance, :default_demand_variance)
                """
            ),
            {
                "default_shift_hours": starter_config["shift_hours"],
                "default_capacity": starter_config["warehouse_capacity"],
                "default_demand_mean": starter_config["demand_distribution_mean"],
                "default_demand_variance": starter_config["demand_distribution_variance"],
                "starter_inventory_total": starter_inventory_total,
            },
        )


def bootstrap_database() -> None:
    from app.models.models import ManufacturingOrder, PurchaseOrder
    from app.services.reference_service import backfill_references

    ensure_schema()

    session = SessionLocal()
    try:
        backfill_references(session, ManufacturingOrder, "MO", "created_date")
        backfill_references(session, PurchaseOrder, "PO", "issue_date")
        session.commit()
    finally:
        session.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
