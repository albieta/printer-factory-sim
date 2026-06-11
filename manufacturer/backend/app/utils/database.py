from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.services.starter_profile import STARTER_INVENTORY, build_starter_config

_db_path = Path(__file__).resolve().parent.parent.parent / "printer_factory_sim.db"
DATABASE_URL = f"sqlite:///{_db_path}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "manufacturing_orders": [
        ("reference_code", "ALTER TABLE manufacturing_orders ADD COLUMN reference_code VARCHAR(32)"),
        ("status_reason", "ALTER TABLE manufacturing_orders ADD COLUMN status_reason VARCHAR(255)"),
    ],
    "purchase_orders": [
        ("reference_code", "ALTER TABLE purchase_orders ADD COLUMN reference_code VARCHAR(32)"),
        ("status_reason", "ALTER TABLE purchase_orders ADD COLUMN status_reason VARCHAR(255)"),
        ("external_order_id", "ALTER TABLE purchase_orders ADD COLUMN external_order_id INTEGER"),
    ],
    "suppliers": [
        ("external_provider_url", "ALTER TABLE suppliers ADD COLUMN external_provider_url VARCHAR(255)"),
        ("external_product_id", "ALTER TABLE suppliers ADD COLUMN external_product_id INTEGER"),
    ],
    "simulation_config": [
        ("assembly_lines", "ALTER TABLE simulation_config ADD COLUMN assembly_lines INTEGER NOT NULL DEFAULT 1"),
        ("workers_per_line", "ALTER TABLE simulation_config ADD COLUMN workers_per_line INTEGER NOT NULL DEFAULT 1"),
        ("shift_hours", "ALTER TABLE simulation_config ADD COLUMN shift_hours FLOAT NOT NULL DEFAULT 8.0"),
        ("sim_day", "ALTER TABLE simulation_config ADD COLUMN sim_day INTEGER NOT NULL DEFAULT 0"),
        ("provider_urls", "ALTER TABLE simulation_config ADD COLUMN provider_urls JSON"),
        ("cost_per_assembly_line_per_day", "ALTER TABLE simulation_config ADD COLUMN cost_per_assembly_line_per_day FLOAT NOT NULL DEFAULT 100.0"),
        ("internal_demand_enabled", "ALTER TABLE simulation_config ADD COLUMN internal_demand_enabled BOOLEAN NOT NULL DEFAULT 0"),
        ("retailer_demand_enabled", "ALTER TABLE simulation_config ADD COLUMN retailer_demand_enabled BOOLEAN NOT NULL DEFAULT 0"),
        ("retailer_demand_mean", "ALTER TABLE simulation_config ADD COLUMN retailer_demand_mean FLOAT NOT NULL DEFAULT 8.0"),
        ("retailer_demand_variance", "ALTER TABLE simulation_config ADD COLUMN retailer_demand_variance FLOAT NOT NULL DEFAULT 2.0"),
        ("retailer_demand_modifier", "ALTER TABLE simulation_config ADD COLUMN retailer_demand_modifier FLOAT NOT NULL DEFAULT 1.0"),
        ("retailer_demand_base_price", "ALTER TABLE simulation_config ADD COLUMN retailer_demand_base_price FLOAT NOT NULL DEFAULT 400.0"),
    ],
    "sales_orders": [
        ("in_progress_day", "ALTER TABLE sales_orders ADD COLUMN in_progress_day INTEGER"),
        ("linked_mfg_order_id", "ALTER TABLE sales_orders ADD COLUMN linked_mfg_order_id VARCHAR(36)"),
    ],
}


def get_db_path() -> Path:
    return Path(__file__).resolve().parents[2] / "printer_factory_sim.db"


def column_exists(connection: Connection, table_name: str, column_name: str) -> bool:
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
                    daily_assembly_hours = COALESCE(assembly_lines, 1) * COALESCE(workers_per_line, 1) * COALESCE(shift_hours, daily_assembly_hours, :default_shift_hours),
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


def apply_external_provider_config(session: Session) -> None:
    """Creates or updates Supplier rows from config.json provider entries."""
    from app.models.models import Product, Supplier
    from app.utils.app_config import get_configured_providers

    for provider in get_configured_providers():
        provider_name = provider.get("name")
        provider_url = provider.get("url")
        products = provider.get("products", [])
        if not provider_name or not provider_url or not isinstance(products, list):
            continue

        for product_config in products:
            product_name = product_config.get("manufacturer_product_name")
            if not product_name:
                continue
            product = session.query(Product).filter(Product.name == product_name).first()
            if product is None:
                continue

            supplier = (
                session.query(Supplier)
                .filter(Supplier.name == provider_name, Supplier.product_id == product.id)
                .first()
            )
            if supplier is None:
                supplier = Supplier(
                    name=provider_name,
                    product_id=product.id,
                    unit_cost=product_config.get("unit_cost", 0),
                    lead_time_days=product_config.get("lead_time_days", 1),
                    quantity_breaks=product_config.get("quantity_breaks"),
                )
                session.add(supplier)

            supplier.external_provider_url = str(provider_url).rstrip("/")
            supplier.external_product_id = product_config.get("external_product_id")
            supplier.unit_cost = product_config.get("unit_cost", supplier.unit_cost)
            supplier.lead_time_days = product_config.get("lead_time_days", supplier.lead_time_days)
            supplier.quantity_breaks = product_config.get("quantity_breaks", supplier.quantity_breaks)


def bootstrap_database() -> None:
    from app.models.models import ManufacturingOrder, PurchaseOrder
    from app.services.reference_service import backfill_references
    from app.services.wholesale_price_service import WholesalePriceService

    ensure_schema()

    session = SessionLocal()
    try:
        backfill_references(session, ManufacturingOrder, "MO", "created_date")
        backfill_references(session, PurchaseOrder, "PO", "issue_date")
        apply_external_provider_config(session)
        session.commit()
        WholesalePriceService(session).ensure_defaults()
        session.commit()
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
