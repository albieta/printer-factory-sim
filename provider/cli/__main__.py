from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Optional

import typer
from sqlalchemy.orm import Session

PROVIDER_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROVIDER_ROOT)
sys.path.insert(0, str(PROVIDER_ROOT))

from app.models.models import OrderStatus  # noqa: E402
from app.services.admin_service import AdminService  # noqa: E402
from app.services.catalog_service import CatalogService  # noqa: E402
from app.services.day_service import DayService  # noqa: E402
from app.services.order_service import OrderService  # noqa: E402
from app.services.sim_state_service import SimStateService  # noqa: E402
from app.services.state_service import StateService  # noqa: E402
from app.utils.database import SessionLocal, bootstrap_database  # noqa: E402


app = typer.Typer(help="Provider CLI for the Week 6 supply-chain simulator.")
orders_app = typer.Typer(help="Order inspection commands.")
price_app = typer.Typer(help="Pricing commands.")
day_app = typer.Typer(help="Simulated-day commands.")

app.add_typer(orders_app, name="orders")
app.add_typer(price_app, name="price")
app.add_typer(day_app, name="day")


@contextmanager
def _session() -> Iterator[Session]:
    bootstrap_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _product_id_for(selector: str) -> int:
    with _session() as db:
        catalog = CatalogService(db)
        if selector.isdigit():
            product = catalog.get_product(int(selector))
        else:
            product = catalog.get_product_by_name(selector)
        if product is None:
            raise typer.BadParameter(f"Product {selector!r} not found")
        return int(product.id)


def _echo_rows(headers: list[str], rows: list[list[object]]) -> None:
    typer.echo(" | ".join(headers))
    typer.echo("-+-".join("-" * len(header) for header in headers))
    for row in rows:
        typer.echo(" | ".join(str(value) for value in row))


@app.command()
def catalog() -> None:
    """List products with lead times, stock, and pricing tiers."""

    with _session() as db:
        rows = []
        for product in CatalogService(db).list_products():
            tiers = ", ".join(
                f"{tier.min_quantity}+ @ {tier.unit_price}"
                for tier in product.pricing_tiers
            )
            rows.append(
                [
                    product.id,
                    product.name,
                    product.lead_time_days,
                    product.stock.quantity if product.stock else 0,
                    tiers,
                ]
            )
        _echo_rows(["id", "product", "lead", "stock", "pricing"], rows)


@app.command()
def stock() -> None:
    """Show current provider inventory."""

    with _session() as db:
        rows = [
            [row.product_id, row.product.name if row.product else "Unknown", row.quantity]
            for row in CatalogService(db).list_stock()
        ]
        _echo_rows(["product_id", "product", "quantity"], rows)


@orders_app.command("list")
def list_orders(status: Optional[OrderStatus] = None) -> None:
    """List provider orders, optionally filtered by status."""

    with _session() as db:
        rows = []
        for order in OrderService(db).list_orders(status=status):
            rows.append(
                [
                    order.id,
                    order.buyer,
                    order.product.name if order.product else order.product_id,
                    order.quantity,
                    order.status.value,
                    order.expected_delivery_day,
                ]
            )
        _echo_rows(["id", "buyer", "product", "qty", "status", "due_day"], rows)


@orders_app.command("show")
def show_order(order_id: int) -> None:
    """Show full details for one order."""

    with _session() as db:
        order = OrderService(db).get_order(order_id)
        if order is None:
            raise typer.BadParameter(f"Order {order_id} not found")
        payload = {
            "id": order.id,
            "buyer": order.buyer,
            "product": order.product.name if order.product else order.product_id,
            "quantity": order.quantity,
            "unit_price": str(order.unit_price),
            "total_price": str(order.total_price),
            "placed_day": order.placed_day,
            "expected_delivery_day": order.expected_delivery_day,
            "shipped_day": order.shipped_day,
            "delivered_day": order.delivered_day,
            "status": order.status.value,
            "status_reason": order.status_reason,
        }
        typer.echo(json.dumps(payload, indent=2))


@price_app.command("set")
def set_price(product: str, tier: int, price: float) -> None:
    """Create or update a product price tier."""

    product_id = _product_id_for(product)
    with _session() as db:
        updated = AdminService(db).set_price(product_id, tier, Decimal(str(price)))
        typer.echo(
            f"Set product {product_id} tier {updated.min_quantity}+ to {updated.unit_price}"
        )


@app.command()
def restock(product: str, quantity: int) -> None:
    """Increase stock for a product."""

    product_id = _product_id_for(product)
    with _session() as db:
        stock_row = AdminService(db).restock(product_id, quantity)
        typer.echo(f"Stock for product {product_id} is now {stock_row.quantity}")


@day_app.command("advance")
def advance_day() -> None:
    """Advance the provider by one simulated day."""

    with _session() as db:
        result = DayService(db).advance()
        typer.echo(json.dumps(result, indent=2))


@day_app.command("current")
def current_day() -> None:
    """Show current provider simulated day."""

    with _session() as db:
        typer.echo(SimStateService(db).get_current_day())


@app.command("export")
def export_state() -> None:
    """Dump full provider state as JSON to stdout."""

    with _session() as db:
        typer.echo(json.dumps(StateService(db).export_state(), indent=2))


@app.command("import")
def import_state(path: Path) -> None:
    """Replace provider state from a JSON snapshot."""

    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    with _session() as db:
        StateService(db).import_state(payload)
    typer.echo(f"Imported provider state from {path}")


def _parse_serve_args(args: list[str]) -> tuple[str, int]:
    host = "0.0.0.0"
    port = 8001
    index = 0

    while index < len(args):
        arg = args[index]
        if arg == "--host":
            index += 1
            if index >= len(args):
                raise typer.BadParameter("--host requires a value")
            host = args[index]
        elif arg.startswith("--host="):
            host = arg.split("=", 1)[1]
        elif arg == "--port":
            index += 1
            if index >= len(args):
                raise typer.BadParameter("--port requires a value")
            port = int(args[index])
        elif arg.startswith("--port="):
            port = int(arg.split("=", 1)[1])
        else:
            raise typer.BadParameter(f"Unknown serve option {arg!r}")
        index += 1

    return host, port


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def serve(ctx: typer.Context) -> None:
    """Start the provider FastAPI server."""

    import uvicorn

    host, port = _parse_serve_args(list(ctx.args))
    uvicorn.run("provider.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
