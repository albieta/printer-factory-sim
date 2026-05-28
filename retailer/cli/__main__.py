"""Retailer CLI — `python -m retailer.cli <command> [args]`.

Global option `--config <path>` loads a JSON config file and sets the
environment variables that the app modules read at import time.  Parse it
from sys.argv *before* the first `from app.*` import so the database URL
and manufacturer URL are known before SQLAlchemy creates the engine.

Config file shape (§4.5 of PRD-week7.md):
  {
    "retailer": {
      "name": "PrinterWorld",
      "port": 8003,
      "db_path": "retailer/data/printerworld.db",
      "manufacturer": {"name": "Factory", "url": "http://localhost:8002"},
      "markup_pct": 30
    }
  }
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import typer
from typing import Any

# ── parse --config before any app.* import ────────────────────────────────────

_RETAILER_ROOT = Path(__file__).resolve().parents[1]

_config: dict[str, Any] = {}
_config_path: Optional[str] = None
for _i, _arg in enumerate(sys.argv[1:], 1):
    if _arg in ("--config",) and _i < len(sys.argv) - 1:
        _config_path = sys.argv[_i + 1]
        break
    if _arg.startswith("--config="):
        _config_path = _arg.split("=", 1)[1]
        break

if _config_path:
    with open(_config_path) as _f:
        _config = json.load(_f)
    _r: dict[str, Any] = _config.get("retailer", {})
    if "db_path" in _r:
        os.environ.setdefault("RETAILER_DB_URL", f"sqlite:///{Path(_r['db_path']).resolve()}")
    _mfr: dict[str, Any] = _r.get("manufacturer", {})
    if "url" in _mfr:
        os.environ.setdefault("RETAILER_MANUFACTURER_URL", _mfr["url"])
    if "name" in _mfr:
        os.environ.setdefault("RETAILER_MANUFACTURER_NAME", _mfr["name"])
    if "name" in _r:
        os.environ.setdefault("RETAILER_NAME", _r["name"])
    if "markup_pct" in _r:
        os.environ.setdefault("RETAILER_MARKUP_PCT", str(_r["markup_pct"]))

# ── app.* imports (safe now that env vars are set) ────────────────────────────

os.chdir(_RETAILER_ROOT)
sys.path.insert(0, str(_RETAILER_ROOT))

from app.models.models import CustomerOrderStatus as ModelCOStatus  # noqa: E402
from app.models.models import PurchaseOrderStatus as ModelPOStatus  # noqa: E402
from app.services.admin_service import export_state, import_state  # noqa: E402
from app.services.catalog_service import CatalogService  # noqa: E402
from app.services.customer_order_service import CustomerOrderService  # noqa: E402
from app.services.day_service import DayService  # noqa: E402
from app.services.manufacturer_client import ManufacturerClient  # noqa: E402
from app.services.purchase_order_service import PurchaseOrderService  # noqa: E402
from app.services.sim_state_service import SimStateService  # noqa: E402
from app.services.starter_profile import MINIMUM_MARKUP_PCT  # noqa: E402
from app.services.stock_service import StockService  # noqa: E402
from app.utils.database import SessionLocal, bootstrap_database  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

# ── Typer app + sub-apps ──────────────────────────────────────────────────────

app = typer.Typer(help="Retailer CLI for the 3D printer supply-chain simulator.")
customers_app = typer.Typer(help="Customer order commands.")
purchase_app = typer.Typer(help="Purchase order commands.")
price_app = typer.Typer(help="Retail pricing commands.")
day_app = typer.Typer(help="Simulated-day commands.")

app.add_typer(customers_app, name="customers")
app.add_typer(purchase_app, name="purchase")
app.add_typer(price_app, name="price")
app.add_typer(day_app, name="day")

_RETAILER_NAME = os.environ.get("RETAILER_NAME", "PrinterWorld")
_MANUFACTURER_NAME = os.environ.get("RETAILER_MANUFACTURER_NAME", "Factory")
_MANUFACTURER_URL = os.environ.get("RETAILER_MANUFACTURER_URL", "http://localhost:8002")
_MARKUP_PCT = MINIMUM_MARKUP_PCT


# ── session helper ────────────────────────────────────────────────────────────

@contextmanager
def _session() -> Iterator[Session]:
    bootstrap_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _client() -> ManufacturerClient:
    return ManufacturerClient(_MANUFACTURER_URL)


def _fmt(headers: list[str], rows: list[list[object]]) -> None:
    typer.echo(" | ".join(headers))
    typer.echo("-+-".join("-" * len(h) for h in headers))
    for row in rows:
        typer.echo(" | ".join(str(v) if v is not None else "-" for v in row))


# ── catalog ───────────────────────────────────────────────────────────────────

@app.command()
def catalog() -> None:
    """List models and retail prices."""
    with _session() as db:
        entries = CatalogService(db).list_catalog()
        _fmt(
            ["model", "retail_price"],
            [[e.product_name, e.retail_price] for e in entries],
        )


# ── stock ─────────────────────────────────────────────────────────────────────

@app.command()
def stock() -> None:
    """Show current finished-printer inventory."""
    with _session() as db:
        items = StockService(db).list_stock()
        _fmt(["model", "quantity"], [[s.product_name, s.quantity] for s in items])


# ── customers ────────────────────────────────────────────────────────────────

@customers_app.command("orders")
def customer_orders(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
) -> None:
    """List customer orders."""
    with _session() as db:
        model_status = ModelCOStatus(status.upper()) if status else None
        orders = CustomerOrderService(db).list_orders(status=model_status)
        _fmt(
            ["id", "customer", "model", "qty", "status", "day"],
            [
                [o.id, o.customer, o.product_name, o.quantity, o.status.value, o.placed_day]
                for o in orders
            ],
        )


@customers_app.command("order")
def customer_order(order_id: int) -> None:
    """Show detail for one customer order."""
    with _session() as db:
        order = CustomerOrderService(db).get_order(order_id)
        if order is None:
            typer.echo(f"Order {order_id} not found.", err=True)
            raise typer.Exit(1)
        typer.echo(json.dumps({
            "id": order.id,
            "customer": order.customer,
            "product_name": order.product_name,
            "quantity": order.quantity,
            "unit_price": str(order.unit_price),
            "total_price": str(order.total_price),
            "placed_day": order.placed_day,
            "fulfilled_day": order.fulfilled_day,
            "status": order.status.value,
            "status_reason": order.status_reason,
        }, indent=2))


@app.command()
def fulfill(order_ids: list[int] = typer.Option(..., "--order", help="Customer order IDs to fulfill")) -> None:
    """Fulfill one or more backordered customer orders from current stock.

    Example: bin/retailer-cli fulfill --order 1001 --order 1002 --order 1003
    """
    if not order_ids:
        typer.echo("No order IDs provided.", err=True)
        raise typer.Exit(1)

    succeeded, failed = [], []
    with _session() as db:
        service = CustomerOrderService(db)
        sim_day = SimStateService(db).get_current_day()

        for order_id in order_ids:
            order = service.get_order(order_id)
            if order is None:
                failed.append((order_id, "Order not found"))
                typer.echo(f"✗ {order_id}: Order not found", err=True)
                continue

            if order.status != ModelCOStatus.BACKORDERED:
                failed.append((order_id, f"Order is {order.status.value}, not BACKORDERED"))
                typer.echo(f"✗ {order_id}: Order is {order.status.value}, not BACKORDERED", err=True)
                continue

            avail = StockService(db).get_quantity(order.product_name)
            if avail < order.quantity:
                failed.append((order_id, f"Insufficient stock: need {order.quantity}, have {avail}"))
                typer.echo(f"✗ {order_id}: Insufficient stock for {order.product_name}", err=True)
                continue

            try:
                # Use auto_fulfil to keep event logic consistent.
                fulfilled = service.auto_fulfil_backorders(sim_day)
                matched = any(o.id == order_id for o in fulfilled)
                if matched:
                    succeeded.append(order_id)
                    typer.echo(f"✓ {order_id} fulfilled")
                else:
                    failed.append((order_id, "Stock consumed by another order"))
                    typer.echo(f"✗ {order_id}: Stock consumed by another order", err=True)
            except Exception as exc:
                failed.append((order_id, str(exc)))
                typer.echo(f"✗ {order_id}: {exc}", err=True)

        db.commit()

    summary = f"Fulfilled {len(succeeded)} / {len(order_ids)} orders"
    if failed:
        summary += f" ({len(failed)} failed)"
    typer.echo(summary)

    if failed and len(failed) == len(order_ids):
        raise typer.Exit(1)


@app.command()
def backorder(order_ids: list[int] = typer.Option(..., "--order", help="Customer order IDs to backorder")) -> None:
    """Mark one or more pending customer orders as backordered.

    Example: bin/retailer-cli backorder --order 2001 --order 2002
    """
    if not order_ids:
        typer.echo("No order IDs provided.", err=True)
        raise typer.Exit(1)

    succeeded, failed = [], []
    with _session() as db:
        sim_day = SimStateService(db).get_current_day()

        for order_id in order_ids:
            try:
                order = CustomerOrderService(db).mark_backordered(order_id, sim_day)
                succeeded.append(order_id)
                typer.echo(f"✓ {order_id} → {order.status.value}")
            except ValueError as exc:
                failed.append((order_id, str(exc)))
                typer.echo(f"✗ {order_id}: {exc}", err=True)
            except Exception as exc:
                failed.append((order_id, str(exc)))
                typer.echo(f"✗ {order_id}: {exc}", err=True)

        db.commit()

    summary = f"Backordered {len(succeeded)} / {len(order_ids)} orders"
    if failed:
        summary += f" ({len(failed)} failed)"
    typer.echo(summary)

    if failed and len(failed) == len(order_ids):
        raise typer.Exit(1)


# ── purchase orders ───────────────────────────────────────────────────────────

@purchase_app.command("list")
def list_purchases(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
) -> None:
    """List purchase orders placed with the manufacturer."""
    with _session() as db:
        model_status = ModelPOStatus(status.upper()) if status else None
        orders = PurchaseOrderService(db, _client()).list_orders(status=model_status)
        _fmt(
            ["id", "model", "qty", "status", "ext_id", "exp_day"],
            [
                [
                    o.id,
                    o.product_name,
                    o.quantity,
                    o.status.value,
                    o.external_order_id,
                    o.expected_delivery_day,
                ]
                for o in orders
            ],
        )


@purchase_app.command("create")
def create_purchase(
    items: list[str] = typer.Option(..., "--item", help="MODEL:QTY")
) -> None:
    """Order one or more printers from the manufacturer.

    Example: bin/retailer-cli purchase create --item Basic300:50 --item Pro450:30 --item Elite700:10
    """
    if not items:
        typer.echo("No purchase items provided.", err=True)
        raise typer.Exit(1)

    succeeded, failed = [], []
    with _session() as db:
        sim_day = SimStateService(db).get_current_day()

        for item in items:
            parts = item.split(":")
            if len(parts) != 2:
                failed.append((item, "Invalid format (expected MODEL:QTY)"))
                typer.echo(f"✗ {item}: Invalid format (expected MODEL:QTY)", err=True)
                continue

            model, qty_str = parts
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

            try:
                order = PurchaseOrderService(db, _client()).place_purchase_order(
                    retailer_name=_RETAILER_NAME,
                    manufacturer_name=_MANUFACTURER_NAME,
                    product_name=model,
                    quantity=qty,
                    sim_day=sim_day,
                )
                succeeded.append(order.id)
                typer.echo(f"✓ {model} ×{qty} → Order #{order.id}")
            except Exception as exc:
                failed.append((item, str(exc)))
                typer.echo(f"✗ {item}: {exc}", err=True)

        db.commit()

    summary = f"Placed {len(succeeded)} / {len(items)} purchase orders"
    if failed:
        summary += f" ({len(failed)} failed)"
    typer.echo(summary)

    if failed and len(failed) == len(items):
        raise typer.Exit(1)


# ── pricing ───────────────────────────────────────────────────────────────────

@price_app.command("set")
def price_set(
    items: list[str] = typer.Option(..., "--item", help="MODEL:PRICE")
) -> None:
    """Set retail prices for one or more models (must meet markup floor).

    Example: bin/retailer-cli price set --item Basic300:445 --item Pro450:925 --item Elite700:1490
    """
    from decimal import Decimal, InvalidOperation

    if not items:
        typer.echo("No price items provided.", err=True)
        raise typer.Exit(1)

    succeeded, failed = [], []
    with _session() as db:
        sim_day = SimStateService(db).get_current_day()

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
                wholesale = _client().get_wholesale_price(model)
            except Exception as exc:
                failed.append((item, f"Could not fetch wholesale price: {exc}"))
                typer.echo(f"✗ {item}: Could not fetch wholesale price: {exc}", err=True)
                continue

            try:
                entry = CatalogService(db).set_retail_price(
                    model,
                    new_price,
                    wholesale_price=wholesale,
                    markup_pct=_MARKUP_PCT,
                    sim_day=sim_day,
                )
                succeeded.append((model, entry.retail_price))
                typer.echo(f"✓ {model} → {entry.retail_price}")
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


# ── day ───────────────────────────────────────────────────────────────────────

@day_app.command("advance")
def advance_day() -> None:
    """Advance the retailer by one simulated day."""
    with _session() as db:
        summary = DayService(db, _client()).advance_day()
        typer.echo(json.dumps(summary, indent=2))


@day_app.command("current")
def current_day() -> None:
    """Show the current simulated day."""
    with _session() as db:
        typer.echo(SimStateService(db).get_current_day())


# ── export / import ───────────────────────────────────────────────────────────

@app.command()
def export(
    output: Optional[Path] = typer.Argument(None, help="File to write (stdout if omitted)"),
) -> None:
    """Dump full retailer state to JSON."""
    with _session() as db:
        data = export_state(db)
    text = json.dumps(data, indent=2, default=str)
    if output:
        output.write_text(text)
        typer.echo(f"State exported to {output}.")
    else:
        typer.echo(text)


@app.command(name="import")
def import_cmd(
    file: Path = typer.Argument(..., help="JSON file produced by `retailer-cli export`"),
) -> None:
    """Load full retailer state from a JSON export file (destructive)."""
    if not file.exists():
        typer.echo(f"File not found: {file}", err=True)
        raise typer.Exit(1)
    data = json.loads(file.read_text())
    with _session() as db:
        import_state(db, data)
        db.commit()
    typer.echo("State imported successfully.")


# ── serve ─────────────────────────────────────────────────────────────────────

@app.command()
def serve(
    port: int = typer.Option(8003, "--port", help="Port to listen on"),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind"),
    config: Optional[Path] = typer.Option(  # noqa: B008 — Typer requires it
        None, "--config", help="Config JSON file (already applied if given above)"
    ),
) -> None:
    """Start the retailer FastAPI server."""
    import uvicorn

    # Port from config file overrides default but --port flag wins.
    if config is None and _config_path is not None:
        _loaded_port = _config.get("retailer", {}).get("port")
        if _loaded_port is not None:
            port = int(_loaded_port)

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        app_dir=str(_RETAILER_ROOT),
        reload=False,
    )


if __name__ == "__main__":
    app()
