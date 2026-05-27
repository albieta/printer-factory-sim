from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import typer
import httpx
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
os.chdir(BACKEND_ROOT)
sys.path.insert(0, str(BACKEND_ROOT))

from app.models.models import Product, SalesOrderStatus, Supplier  # noqa: E402
from app.schemas.schemas import PurchaseOrderCreate  # noqa: E402
from app.services.config_service import ConfigService  # noqa: E402
from app.services.inventory_service import InventoryService  # noqa: E402
from app.services.sales_order_service import SalesOrderService  # noqa: E402
from app.services.simulation_service import SimulationService  # noqa: E402
from app.services.supplier_service import PurchaseOrderService, SupplierService  # noqa: E402
from app.services.wholesale_price_service import WholesalePriceService  # noqa: E402
from app.utils.database import SessionLocal, bootstrap_database  # noqa: E402


app = typer.Typer(help="Manufacturer CLI for the 3D printer factory simulator.")
suppliers_app = typer.Typer(help="Supplier commands.")
purchase_app = typer.Typer(help="Purchase-order commands.")
day_app = typer.Typer(help="Simulated-day commands.")
sales_app = typer.Typer(help="Inbound sales-order commands.")
production_app = typer.Typer(help="Production management commands.")
price_app = typer.Typer(help="Wholesale pricing commands.")

app.add_typer(suppliers_app, name="suppliers")
app.add_typer(purchase_app, name="purchase")
app.add_typer(day_app, name="day")
app.add_typer(sales_app, name="sales")
app.add_typer(production_app, name="production")
app.add_typer(price_app, name="price")


@contextmanager
def _session() -> Iterator[Session]:
    bootstrap_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _echo_rows(headers: list[str], rows: list[list[object]]) -> None:
    typer.echo(" | ".join(headers))
    typer.echo("-+-".join("-" * len(header) for header in headers))
    for row in rows:
        typer.echo(" | ".join(str(value) for value in row))


def _find_supplier(db: Session, name: str) -> list[Supplier]:
    return db.query(Supplier).filter(Supplier.name == name).all()


def _find_product(db: Session, selector: str) -> Product | None:
    product = db.query(Product).filter(Product.id == selector).first()
    if product is not None:
        return product
    return db.query(Product).filter(Product.name == selector).first()


@suppliers_app.command("list")
def list_suppliers() -> None:
    """List manufacturer-side suppliers."""

    with _session() as db:
        service = SupplierService(db)
        rows = []
        for supplier in service.get_all_suppliers():
            item = service.serialize_supplier(supplier)
            rows.append(
                [
                    item["id"],
                    item["name"],
                    item["product_name"],
                    item["unit_cost"],
                    item["lead_time_days"],
                    item["external_provider_url"] or "-",
                ]
            )
        _echo_rows(["id", "supplier", "product", "unit_cost", "lead", "external"], rows)


@suppliers_app.command("catalog")
def supplier_catalog(supplier_name: str) -> None:
    """Show products and internal price breaks for one supplier."""

    with _session() as db:
        suppliers = _find_supplier(db, supplier_name)
        if not suppliers:
            raise typer.BadParameter(f"Supplier {supplier_name!r} not found")

        external_supplier = next((row for row in suppliers if row.external_provider_url), None)
        if external_supplier is not None:
            assert external_supplier.external_provider_url is not None
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(f"{external_supplier.external_provider_url.rstrip('/')}/api/catalog")
                    response.raise_for_status()
            except httpx.HTTPError as exc:
                raise typer.BadParameter(f"Provider catalog request failed: {exc}") from exc

            products = response.json().get("products", [])
            rows = [
                [
                    product.get("id"),
                    product.get("name"),
                    product.get("lead_time_days"),
                    product.get("stock_quantity"),
                    ", ".join(
                        f"{tier['min_quantity']}+ @ {tier['unit_price']}"
                        for tier in product.get("pricing_tiers", [])
                    ),
                ]
                for product in products
            ]
            _echo_rows(["provider_id", "product", "lead", "stock", "tiers"], rows)
            return

        rows = []
        for supplier in suppliers:
            tiers = "base"
            if supplier.quantity_breaks:
                tiers = ", ".join(
                    f"{tier['qty']}+ @ {tier['price']}"
                    for tier in supplier.quantity_breaks
                )
            rows.append(
                [
                    supplier.product_id,
                    supplier.product.name if supplier.product else "Unknown",
                    supplier.unit_cost,
                    supplier.lead_time_days,
                    tiers,
                ]
            )
        _echo_rows(["product_id", "product", "base_cost", "lead", "breaks"], rows)


@purchase_app.command("create")
def create_purchase(
    items: list[str] = typer.Option(..., "--item", help="SUPPLIER:PRODUCT:QTY")
) -> None:
    """Create one or more manufacturer purchase orders.

    Example: bin/manufacturer-cli purchase create --item "ChipSupply Co:Control Board:100" --item "Fastparts:Stepper Motor:50"
    """
    if not items:
        typer.echo("No purchase items provided.", err=True)
        raise typer.Exit(1)

    succeeded, failed = [], []
    with _session() as db:
        for item in items:
            parts = item.split(":")
            if len(parts) != 3:
                failed.append((item, "Invalid format (expected SUPPLIER:PRODUCT:QTY)"))
                typer.echo(f"✗ {item}: Invalid format (expected SUPPLIER:PRODUCT:QTY)", err=True)
                continue

            supplier, product, qty_str = parts
            try:
                qty = int(qty_str)
            except ValueError:
                failed.append((item, f"Invalid quantity: {qty_str!r}"))
                typer.echo(f"✗ {item}: Invalid quantity {qty_str!r}", err=True)
                continue

            if qty <= 0:
                failed.append((item, "Quantity must be positive"))
                typer.echo(f"✗ {item}: Quantity must be positive", err=True)
                continue

            product_row = _find_product(db, product)
            if product_row is None:
                failed.append((item, f"Product {product!r} not found"))
                typer.echo(f"✗ {item}: Product {product!r} not found", err=True)
                continue

            matching_suppliers = [
                row
                for row in _find_supplier(db, supplier)
                if row.product_id == product_row.id
            ]
            if not matching_suppliers:
                failed.append((item, f"Supplier {supplier!r} does not sell {product_row.name!r}"))
                typer.echo(f"✗ {item}: Supplier {supplier!r} does not sell {product_row.name!r}", err=True)
                continue

            try:
                sim_date = ConfigService(db).get_sim_date()
                order = PurchaseOrderService(db).create_purchase_order(
                    PurchaseOrderCreate(
                        supplier_id=matching_suppliers[0].id,
                        product_id=product_row.id,
                        quantity=qty,
                    ),
                    sim_date,
                )
                succeeded.append(order.reference_code)
                typer.echo(f"✓ {order.reference_code}: {product} ×{qty}")
            except Exception as exc:
                failed.append((item, str(exc)))
                typer.echo(f"✗ {item}: {exc}", err=True)

        db.commit()

    summary = f"Created {len(succeeded)} / {len(items)} purchase orders"
    if failed:
        summary += f" ({len(failed)} failed)"
    typer.echo(summary)

    if failed and len(failed) == len(items):
        raise typer.Exit(1)


@purchase_app.command("list")
def list_purchase_orders() -> None:
    """List manufacturer purchase orders."""

    with _session() as db:
        service = PurchaseOrderService(db)
        rows = []
        for order in service.get_all_purchase_orders():
            item = service.serialize_purchase_order(order)
            rows.append(
                [
                    item["reference_code"],
                    item["supplier_name"],
                    item["product_name"],
                    item["quantity"],
                    item["status"].value,
                    item["expected_delivery"],
                ]
            )
        _echo_rows(["ref", "supplier", "product", "qty", "status", "due"], rows)


@app.command()
def inventory() -> None:
    """Show current material inventory."""

    with _session() as db:
        rows = [
            [
                item["product_name"],
                item["quantity"],
                item["pending_inbound_quantity"],
                item["accepted_order_demand"],
            ]
            for item in InventoryService(db).get_inventory_snapshot()
        ]
        _echo_rows(["product", "on_hand", "inbound", "demand"], rows)


@day_app.command("advance")
def advance_day() -> None:
    """Advance the manufacturer by one simulated day."""

    with _session() as db:
        typer.echo(json.dumps(SimulationService(db).advance_day(), indent=2, default=str))


@day_app.command("current")
def current_day() -> None:
    """Show current manufacturer simulation date."""

    with _session() as db:
        typer.echo(ConfigService(db).get_sim_date().isoformat())


# ── sales orders ─────────────────────────────────────────────────────────────

@sales_app.command("orders")
def sales_orders(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
) -> None:
    """List inbound sales orders from retailers."""
    with _session() as db:
        model_status = SalesOrderStatus(status.upper()) if status else None
        orders = SalesOrderService(db).list_orders(status=model_status)
        _echo_rows(
            ["ref", "retailer", "model", "qty", "status", "day"],
            [
                [
                    o.reference_code or o.id[:8],
                    o.retailer_name,
                    o.product.name if o.product else "?",
                    o.quantity,
                    o.status.value,
                    o.placed_day,
                ]
                for o in orders
            ],
        )


@sales_app.command("order")
def sales_order(order_id: str) -> None:
    """Show detail for one sales order."""
    with _session() as db:
        order = SalesOrderService(db).get_order(order_id)
        if order is None:
            typer.echo(f"Sales order {order_id!r} not found.", err=True)
            raise typer.Exit(1)
        typer.echo(json.dumps(SalesOrderService(db).serialize_order(order), indent=2))


# ── production ────────────────────────────────────────────────────────────────

@production_app.command("release")
def production_release(order_ids: list[str] = typer.Option(..., "--order", help="Sales order IDs to release")) -> None:
    """Release one or more PENDING sales orders to production.

    Example: bin/manufacturer-cli production release --order SO-001 --order SO-002 --order SO-003
    """
    if not order_ids:
        typer.echo("No order IDs provided.", err=True)
        raise typer.Exit(1)

    succeeded, failed = [], []
    with _session() as db:
        for order_id in order_ids:
            result = SalesOrderService(db).release_to_production(order_id)
            if not result["success"]:
                failed.append((order_id, result.get('error', 'Unknown error')))
                typer.echo(f"✗ {order_id}: {result.get('error')}", err=True)
            else:
                order = result["order"]
                succeeded.append(order_id)
                typer.echo(f"✓ {order_id} → {order.status.value}")
        db.commit()

    summary = f"Released {len(succeeded)} / {len(order_ids)} orders"
    if failed:
        summary += f" ({len(failed)} failed)"
    typer.echo(summary)

    if failed and len(failed) == len(order_ids):
        raise typer.Exit(1)


@production_app.command("status")
def production_status() -> None:
    """Show all active (non-terminal) sales orders."""
    with _session() as db:
        active = SalesOrderService(db).get_production_status()
        if not active:
            typer.echo("No active production orders.")
            return
        _echo_rows(
            ["ref", "retailer", "model", "qty", "status", "day"],
            [
                [
                    o.get("reference_code") or o["id"][:8],
                    o["retailer"],
                    o.get("model", "?"),
                    o["quantity"],
                    o["status"],
                    o["placed_day"],
                ]
                for o in active
            ],
        )


# ── capacity ──────────────────────────────────────────────────────────────────

@app.command()
def capacity() -> None:
    """Show daily assembly capacity and current utilisation."""
    with _session() as db:
        cfg = ConfigService(db).get_config()
        inv = InventoryService(db).get_capacity_info()
        _echo_rows(
            ["metric", "value"],
            [
                ["assembly_lines", cfg.assembly_lines],
                ["workers_per_line", cfg.workers_per_line],
                ["shift_hours", cfg.shift_hours],
                ["daily_assembly_hours", cfg.daily_assembly_hours],
                ["warehouse_capacity", inv["warehouse_capacity"]],
                ["current_usage", f"{inv['current_usage']:.1f}"],
                ["available_capacity", f"{inv['available_capacity']:.1f}"],
                ["usage_pct", f"{inv['usage_percentage']:.1f}%"],
            ],
        )


@app.command()
def open_assembly_line() -> None:
    """Open a new parallel assembly line (records setup cost in financials)."""
    from app.schemas.schemas import SimulationConfigUpdate
    from app.services.financial_service import FinancialService

    with _session() as db:
        cfg = ConfigService(db).get_config()
        new_lines = cfg.assembly_lines + 1
        updated = ConfigService(db).update_config(SimulationConfigUpdate(assembly_lines=new_lines))
        FinancialService(db).record_assembly_line_opened(cfg.sim_day)
        typer.echo(
            f"Assembly line opened (cost recorded). "
            f"Total lines: {updated.assembly_lines}, "
            f"Daily capacity: {updated.daily_assembly_hours:.1f} hours"
        )


@app.command()
def hire_worker() -> None:
    """Hire one additional worker per line (records first-day wage cost in financials).

    Workers are shared across ALL assembly lines — hiring 1 worker
    adds 1 worker to every line, increasing total workers by assembly_lines.
    """
    from app.schemas.schemas import SimulationConfigUpdate
    from app.services.financial_service import FinancialService

    with _session() as db:
        cfg = ConfigService(db).get_config()
        if cfg.workers_per_line >= cfg.max_workers_per_line:
            typer.echo(
                f"Cannot hire: already at max {cfg.max_workers_per_line} workers/line.", err=True
            )
            raise typer.Exit(1)
        new_workers = cfg.workers_per_line + 1
        updated = ConfigService(db).update_config(SimulationConfigUpdate(workers_per_line=new_workers))
        FinancialService(db).record_worker_hired(cfg.sim_day)
        typer.echo(
            f"Worker hired (cost recorded). "
            f"Workers per line: {updated.workers_per_line} × {updated.assembly_lines} lines = "
            f"{updated.workers_per_line * updated.assembly_lines} total workers, "
            f"Daily capacity: {updated.daily_assembly_hours:.1f} hours"
        )


@app.command()
def fire_worker() -> None:
    """Fire one worker per line (reduce workers/line, minimum 1)."""
    from app.schemas.schemas import SimulationConfigUpdate
    from app.services.financial_service import FinancialService

    with _session() as db:
        cfg = ConfigService(db).get_config()
        if cfg.workers_per_line <= 1:
            typer.echo("Cannot fire workers. Minimum of 1 worker per line required.", err=True)
            raise typer.Exit(1)

        new_workers = cfg.workers_per_line - 1
        updated = ConfigService(db).update_config(SimulationConfigUpdate(workers_per_line=new_workers))
        FinancialService(db).record_worker_fired(cfg.sim_day)
        typer.echo(
            f"Worker fired. "
            f"Workers per line: {updated.workers_per_line} × {updated.assembly_lines} lines = "
            f"{updated.workers_per_line * updated.assembly_lines} total workers, "
            f"Daily capacity: {updated.daily_assembly_hours:.1f} hours"
        )


@app.command()
def close_assembly_line() -> None:
    """Close an assembly line (minimum 1 line, records closure in financials)."""
    from app.schemas.schemas import SimulationConfigUpdate
    from app.services.financial_service import FinancialService

    with _session() as db:
        cfg = ConfigService(db).get_config()
        if cfg.assembly_lines <= 1:
            typer.echo("Cannot close assembly lines. Minimum of 1 line required.", err=True)
            raise typer.Exit(1)

        new_lines = cfg.assembly_lines - 1
        updated = ConfigService(db).update_config(SimulationConfigUpdate(assembly_lines=new_lines))
        FinancialService(db).record_assembly_line_closed(cfg.sim_day)
        typer.echo(
            f"Assembly line closed. "
            f"Total lines: {updated.assembly_lines}, "
            f"Daily capacity: {updated.daily_assembly_hours:.1f} hours"
        )


# ── wholesale prices ──────────────────────────────────────────────────────────

@price_app.command("list")
def price_list() -> None:
    """Show wholesale prices for all printer models."""
    with _session() as db:
        prices = WholesalePriceService(db).list_prices()
        _echo_rows(["model", "wholesale_price"], [[name, str(p)] for name, p in prices.items()])


@price_app.command("set")
def price_set(
    items: list[str] = typer.Option(..., "--item", help="MODEL:PRICE")
) -> None:
    """Set wholesale prices for one or more printer models.

    Example: bin/manufacturer-cli price set --item Basic300:450 --item Pro450:950 --item Elite700:1540
    """
    from decimal import Decimal, InvalidOperation

    if not items:
        typer.echo("No price items provided.", err=True)
        raise typer.Exit(1)

    succeeded, failed = [], []
    with _session() as db:
        for item in items:
            parts = item.split(":")
            if len(parts) != 2:
                failed.append((item, "Invalid format (expected MODEL:PRICE)"))
                typer.echo(f"✗ {item}: Invalid format (expected MODEL:PRICE)", err=True)
                continue

            model, price_str = parts
            try:
                new_price = Decimal(price_str)
            except (InvalidOperation, ValueError):
                failed.append((item, f"Invalid price: {price_str!r}"))
                typer.echo(f"✗ {item}: Invalid price {price_str!r}", err=True)
                continue

            try:
                result = WholesalePriceService(db).set_price(model, new_price)
                succeeded.append((model, result['price']))
                typer.echo(f"✓ {model} → {result['price']}")
            except ValueError as exc:
                failed.append((item, str(exc)))
                typer.echo(f"✗ {item}: {exc}", err=True)

        db.commit()

    summary = f"Set {len(succeeded)} / {len(items)} prices"
    if failed:
        summary += f" ({len(failed)} failed)"
    typer.echo(summary)

    if failed and len(failed) == len(items):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
