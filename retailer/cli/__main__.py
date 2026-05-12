"""Retailer CLI — `python -m retailer.cli`.

Full command surface from `docs/PRD-week7.md` §4.5. All commands share
the `--config` global option so multiple retailer instances can be driven
from the same terminal by pointing at different config files.
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Optional

import typer
from sqlalchemy.orm import Session

# ── path bootstrap ────────────────────────────────────────────────────────────
RETAILER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RETAILER_ROOT))

from app.models.models import CustomerOrderStatus  # noqa: E402
from app.services.admin_service import AdminService  # noqa: E402
from app.services.catalog_service import CatalogError, CatalogService, ModelNotFoundError  # noqa: E402
from app.services.day_service import DayService  # noqa: E402
from app.services.order_service import OrderError, OrderService  # noqa: E402
from app.services.purchase_service import PurchaseError, PurchaseService  # noqa: E402
from app.services.sim_state_service import SimStateService  # noqa: E402
from app.services.stock_service import StockService  # noqa: E402
from app.utils.config import RetailerConfig, load_config  # noqa: E402
from app.utils.database import bootstrap_database, get_session_factory  # noqa: E402

# ── app & shared state ────────────────────────────────────────────────────────

app = typer.Typer(
    help="Retailer CLI for the Week 7 supply-chain simulator.",
    no_args_is_help=True,
)
customers_app = typer.Typer(help="Customer order commands.")
purchase_app = typer.Typer(help="Purchase order commands (retailer → manufacturer).")
price_app = typer.Typer(help="Retail price commands.")
day_app = typer.Typer(help="Simulated-day commands.")

app.add_typer(customers_app, name="customers")
app.add_typer(purchase_app, name="purchase")
app.add_typer(price_app, name="price")
app.add_typer(day_app, name="day")

_cfg: Optional[RetailerConfig] = None


@app.callback()
def _init(
    config: Path = typer.Option(
        Path("retailer.json"),
        "--config",
        "-c",
        help="Path to retailer config JSON.",
        show_default=True,
    ),
) -> None:
    """Load config and bootstrap the database before any command runs."""
    global _cfg
    _cfg = load_config(config)
    bootstrap_database(_cfg.db_path)


@contextmanager
def _session() -> Iterator[Session]:
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def _require_cfg() -> RetailerConfig:
    assert _cfg is not None, "config not initialised"
    return _cfg


# ── catalog ───────────────────────────────────────────────────────────────────


@app.command()
def catalog() -> None:
    """List printer models with their current retail prices."""
    with _session() as db:
        items = CatalogService(db).list_items()
        result = [
            {"model_name": i.model_name, "retail_price": float(i.retail_price)}
            for i in items
        ]
    typer.echo(json.dumps(result, indent=2))


# ── stock ─────────────────────────────────────────────────────────────────────


@app.command()
def stock() -> None:
    """Show current finished-printer inventory."""
    with _session() as db:
        rows = StockService(db).list_stock()
        result = [
            {
                "model_name": item.model_name,
                "quantity": s.quantity if s is not None else 0,
            }
            for item, s in rows
        ]
    typer.echo(json.dumps(result, indent=2))


# ── customer order commands ───────────────────────────────────────────────────


@customers_app.command("orders")
def customers_orders(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status."),
) -> None:
    """List customer orders, optionally filtered by status."""
    with _session() as db:
        model_status: Optional[CustomerOrderStatus] = None
        if status:
            try:
                model_status = CustomerOrderStatus(status.upper())
            except ValueError:
                typer.echo(f"Unknown status: {status}", err=True)
                raise typer.Exit(1)
        orders = OrderService(db).list_orders(status=model_status)
        result = [
            {
                "id": o.id,
                "model_name": o.catalog_item.model_name,
                "quantity": o.quantity,
                "placed_day": o.placed_day,
                "status": o.status.value,
            }
            for o in orders
        ]
    typer.echo(json.dumps(result, indent=2))


@customers_app.command("order")
def customers_order(order_id: int = typer.Argument(..., help="Customer order ID.")) -> None:
    """Show details for one customer order."""
    with _session() as db:
        order = OrderService(db).get_order(order_id)
        if order is None:
            typer.echo(f"Order {order_id} not found.", err=True)
            raise typer.Exit(1)
        result = {
            "id": order.id,
            "model_name": order.catalog_item.model_name,
            "quantity": order.quantity,
            "unit_price": float(order.unit_price),
            "total_price": float(order.total_price),
            "placed_day": order.placed_day,
            "fulfilled_day": order.fulfilled_day,
            "status": order.status.value,
        }
    typer.echo(json.dumps(result, indent=2))


# ── manual fulfill / backorder ────────────────────────────────────────────────


@app.command()
def fulfill(order_id: int = typer.Argument(..., help="Customer order ID to fulfill.")) -> None:
    """Manually ship a pending or backordered order from stock."""
    with _session() as db:
        try:
            order = OrderService(db).fulfill(order_id)
            msg = f"Order {order.id} fulfilled on day {order.fulfilled_day}."
        except OrderError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
    typer.echo(msg)


@app.command()
def backorder(order_id: int = typer.Argument(..., help="Customer order ID to backorder.")) -> None:
    """Manually mark a pending order as backordered."""
    with _session() as db:
        try:
            order = OrderService(db).mark_backordered(order_id)
            msg = f"Order {order.id} marked as backordered."
        except OrderError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
    typer.echo(msg)


# ── purchase orders ───────────────────────────────────────────────────────────


@purchase_app.command("list")
def purchase_list() -> None:
    """List purchase orders placed with the manufacturer."""
    with _session() as db:
        pos = PurchaseService(db, _require_cfg().manufacturer.url).list_orders()
        result = [
            {
                "id": po.id,
                "model_name": po.catalog_item.model_name,
                "quantity": po.quantity,
                "placed_day": po.placed_day,
                "expected_delivery_day": po.expected_delivery_day,
                "status": po.status.value,
            }
            for po in pos
        ]
    typer.echo(json.dumps(result, indent=2))


@purchase_app.command("create")
def purchase_create(
    model: str = typer.Argument(..., help="Printer model name."),
    qty: int = typer.Argument(..., help="Number of units to order."),
) -> None:
    """Order finished printers from the manufacturer."""
    cfg = _require_cfg()
    with _session() as db:
        try:
            po = PurchaseService(db, cfg.manufacturer.url).create(model, qty, cfg.name)
            msg = (
                f"Purchase order {po.id} placed: {qty}× {model}, "
                f"expected delivery day {po.expected_delivery_day}."
            )
        except ModelNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        except PurchaseError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        except Exception as exc:
            typer.echo(f"Error contacting manufacturer: {exc}", err=True)
            raise typer.Exit(1)
    typer.echo(msg)


# ── price ─────────────────────────────────────────────────────────────────────


@price_app.command("set")
def price_set(
    model: str = typer.Argument(..., help="Printer model name."),
    price: float = typer.Argument(..., help="New retail price."),
) -> None:
    """Set the retail price for a model (minimum 15 % above manufacturer wholesale)."""
    cfg = _require_cfg()
    with _session() as db:
        try:
            item = CatalogService(db).set_price(model, Decimal(str(price)), cfg.manufacturer.url)
            db.commit()
            msg = f"Retail price for {item.model_name!r} set to {float(item.retail_price):.2f}."
        except ModelNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        except CatalogError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
    typer.echo(msg)


# ── day ───────────────────────────────────────────────────────────────────────


@day_app.command("advance")
def day_advance() -> None:
    """Advance the retailer's simulated day by one."""
    cfg = _require_cfg()
    with _session() as db:
        try:
            result = DayService(db, cfg.manufacturer.url).advance()
            msg = (
                f"Day {result.previous_day} → {result.current_day}. "
                f"Deliveries: {result.deliveries_received}. "
                f"Backorders fulfilled: {result.backorders_fulfilled}."
            )
        except Exception as exc:
            typer.echo(f"Error during day advance: {exc}", err=True)
            raise typer.Exit(1)
    typer.echo(msg)


@day_app.command("current")
def day_current() -> None:
    """Show the current simulated day."""
    with _session() as db:
        day = SimStateService(db).get_current_day()
    typer.echo(json.dumps({"current_day": day}))


# ── export / import ───────────────────────────────────────────────────────────


@app.command("export")
def export_cmd() -> None:
    """Dump full retailer state to JSON (stdout)."""
    with _session() as db:
        data = AdminService(db).export_state()
    typer.echo(json.dumps(data, indent=2, default=str))


@app.command("import")
def import_cmd(
    file: Path = typer.Argument(..., help="Path to a JSON state file.")
) -> None:
    """Load retailer state from a JSON file, replacing all existing data."""
    data = json.loads(file.read_text())
    with _session() as db:
        AdminService(db).import_state(data)
    typer.echo("State imported successfully.")


# ── serve ─────────────────────────────────────────────────────────────────────


@app.command()
def serve(
    config: Path = typer.Option(
        Path("retailer.json"),
        "--config",
        "-c",
        help="Path to retailer config JSON.",
    ),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Override port from config."),
) -> None:
    """Start the retailer FastAPI server."""
    import os

    import uvicorn

    cfg = load_config(config)
    effective_port = port if port is not None else cfg.port
    os.environ["RETAILER_CONFIG"] = str(config.resolve())
    uvicorn.run(
        "retailer.main:app",
        host="0.0.0.0",
        port=effective_port,
        reload=False,
    )


if __name__ == "__main__":
    app()
