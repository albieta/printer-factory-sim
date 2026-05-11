from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import typer
import httpx
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
os.chdir(BACKEND_ROOT)
sys.path.insert(0, str(BACKEND_ROOT))

from app.models.models import Product, Supplier  # noqa: E402
from app.schemas.schemas import PurchaseOrderCreate  # noqa: E402
from app.services.config_service import ConfigService  # noqa: E402
from app.services.inventory_service import InventoryService  # noqa: E402
from app.services.sales_service import ModelNotFoundError, SalesService  # noqa: E402
from app.services.simulation_service import SimulationService  # noqa: E402
from app.services.supplier_service import PurchaseOrderService, SupplierService  # noqa: E402
from app.utils.database import SessionLocal, bootstrap_database  # noqa: E402


app = typer.Typer(help="Manufacturer CLI for the 3D printer factory simulator.")
suppliers_app = typer.Typer(help="Supplier commands.")
purchase_app = typer.Typer(help="Purchase-order commands.")
day_app = typer.Typer(help="Simulated-day commands.")
sales_app = typer.Typer(help="Sales order commands (retailer purchases).")
price_app = typer.Typer(help="Wholesale price commands.")

app.add_typer(suppliers_app, name="suppliers")
app.add_typer(purchase_app, name="purchase")
app.add_typer(day_app, name="day")
app.add_typer(sales_app, name="sales")
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
    supplier: str = typer.Option(..., "--supplier"),
    product: str = typer.Option(..., "--product"),
    qty: int = typer.Option(..., "--qty"),
) -> None:
    """Create a manufacturer purchase order."""

    if qty <= 0:
        raise typer.BadParameter("qty must be positive")

    with _session() as db:
        product_row = _find_product(db, product)
        if product_row is None:
            raise typer.BadParameter(f"Product {product!r} not found")

        matching_suppliers = [
            row
            for row in _find_supplier(db, supplier)
            if row.product_id == product_row.id
        ]
        if not matching_suppliers:
            raise typer.BadParameter(
                f"Supplier {supplier!r} does not sell product {product_row.name!r}"
            )

        sim_date = ConfigService(db).get_sim_date()
        order = PurchaseOrderService(db).create_purchase_order(
            PurchaseOrderCreate(
                supplier_id=matching_suppliers[0].id,
                product_id=product_row.id,
                quantity=qty,
            ),
            sim_date,
        )
        payload = PurchaseOrderService(db).serialize_purchase_order(order)
        typer.echo(json.dumps(payload, indent=2, default=str))


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


@sales_app.command("list")
def sales_list() -> None:
    """List sales orders placed by retailers."""
    with _session() as db:
        svc = SalesService(db)
        orders = svc.list_orders()
        rows = [
            [
                o.id,
                o.product.name if o.product else "?",
                o.quantity,
                o.buyer_name,
                o.placed_day,
                o.expected_delivery_day,
                o.status.value,
            ]
            for o in orders
        ]
    _echo_rows(["id", "model", "qty", "buyer", "placed", "due", "status"], rows)


@sales_app.command("show")
def sales_show(order_id: int = typer.Argument(..., help="Sales order ID.")) -> None:
    """Show details for one sales order."""
    with _session() as db:
        order = SalesService(db).get_order(order_id)
        if order is None:
            typer.echo(f"Sales order {order_id} not found.", err=True)
            raise typer.Exit(1)
        data = {
            "id": order.id,
            "model": order.product.name if order.product else None,
            "quantity": order.quantity,
            "buyer_name": order.buyer_name,
            "unit_price": float(order.unit_price),
            "total_price": float(order.total_price),
            "placed_day": order.placed_day,
            "expected_delivery_day": order.expected_delivery_day,
            "delivered_day": order.delivered_day,
            "status": order.status.value,
        }
    typer.echo(json.dumps(data, indent=2))


@price_app.command("list")
def price_list() -> None:
    """List wholesale prices for all printer models."""
    with _session() as db:
        wps = SalesService(db).list_prices()
        rows = [
            [wp.product.name if wp.product else "?", float(wp.price), wp.lead_time_days]
            for wp in wps
        ]
    _echo_rows(["model", "wholesale_price", "lead_time_days"], rows)


@price_app.command("set")
def price_set(
    model: str = typer.Argument(..., help="Printer model name."),
    price: float = typer.Argument(..., help="New wholesale price."),
    lead_time: int = typer.Option(3, "--lead-time", "-l", help="Lead time in days."),
) -> None:
    """Set the wholesale price (and lead time) for a printer model."""
    from decimal import Decimal

    with _session() as db:
        try:
            svc = SalesService(db)
            wp = svc.set_price(model, Decimal(str(price)), lead_time)
            db.commit()
            model_name = wp.product.name if wp.product else model
            msg = f"Wholesale price for {model_name!r}: ${float(wp.price):.2f}, {wp.lead_time_days}d lead."
        except ModelNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
    typer.echo(msg)


if __name__ == "__main__":
    app()
