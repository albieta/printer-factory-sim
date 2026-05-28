from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.models.models import (
    BillOfMaterials,
    Event,
    EventType,
    FinancialTransaction,
    FinancialTransactionType,
    Inventory,
    ManufacturingOrder,
    OrderStatus,
    Product,
    ProductType,
    PurchaseOrder,
    PurchaseOrderStatus,
    SalesOrder,
    SalesOrderStatus,
    SimulationConfig,
    Supplier,
    WholesalePrice,
)
from app.schemas.schemas import ImportResult
from app.services.config_service import ConfigService
from app.services.inventory_service import InventoryService
from app.services.presentation_service import serialize_manufacturing_order, serialize_purchase_order
from app.utils.database import get_db

router = APIRouter()


def make_attachment_response(payload: dict[str, Any], filename: str) -> JSONResponse:
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value


def serialize_product(product: Product) -> dict[str, Any]:
    return {
        "id": product.id,
        "name": product.name,
        "type": product.type,
        "assembly_hours": product.assembly_hours,
        "created_at": product.created_at,
    }


def serialize_bom_entry(entry: BillOfMaterials) -> dict[str, Any]:
    return {
        "id": entry.id,
        "finished_product_id": entry.finished_product_id,
        "finished_product_name": entry.finished_product.name if entry.finished_product else None,
        "material_id": entry.material_id,
        "material_name": entry.material.name if entry.material else None,
        "quantity": entry.quantity,
    }


def serialize_supplier(supplier: Supplier) -> dict[str, Any]:
    return {
        "id": supplier.id,
        "name": supplier.name,
        "product_id": supplier.product_id,
        "product_name": supplier.product.name if supplier.product else None,
        "unit_cost": supplier.unit_cost,
        "lead_time_days": supplier.lead_time_days,
        "quantity_breaks": supplier.quantity_breaks,
        "external_provider_url": supplier.external_provider_url,
        "external_product_id": supplier.external_product_id,
    }


def serialize_event(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "sim_date": event.sim_date,
        "timestamp": event.timestamp,
        "details": event.details or {},
    }


def serialize_sales_order(order: SalesOrder) -> dict[str, Any]:
    return {
        "id": order.id,
        "reference_code": order.reference_code,
        "retailer_name": order.retailer_name,
        "product_id": order.product_id,
        "product_name": order.product.name if order.product else None,
        "quantity": order.quantity,
        "status": order.status,
        "status_reason": order.status_reason,
        "unit_price": order.unit_price,
        "total_price": order.total_price,
        "placed_day": order.placed_day,
        "expected_ship_day": order.expected_ship_day,
        "in_progress_day": order.in_progress_day,
        "shipped_day": order.shipped_day,
        "delivered_day": order.delivered_day,
        "linked_mfg_order_id": order.linked_mfg_order_id,
        "created_at": order.created_at,
    }


def serialize_wholesale_price(wp: WholesalePrice) -> dict[str, Any]:
    return {
        "product_id": wp.product_id,
        "product_name": wp.product.name if wp.product else None,
        "price": wp.price,
        "updated_at": wp.updated_at,
    }


def serialize_financial_transaction(txn: FinancialTransaction) -> dict[str, Any]:
    return {
        "id": txn.id,
        "transaction_type": txn.transaction_type,
        "amount": txn.amount,
        "description": txn.description,
        "sim_day": txn.sim_day,
        "created_at": txn.created_at,
    }


@router.get("/export/full-state/")
def export_full_state(db: Session = Depends(get_db)):
    inventory_service = InventoryService(db)

    products = db.query(Product).order_by(Product.name.asc()).all()
    bom_entries = (
        db.query(BillOfMaterials)
        .options(
            joinedload(BillOfMaterials.finished_product),
            joinedload(BillOfMaterials.material),
        )
        .all()
    )
    suppliers = db.query(Supplier).options(joinedload(Supplier.product)).order_by(Supplier.name.asc()).all()
    manufacturing_orders = (
        db.query(ManufacturingOrder)
        .options(joinedload(ManufacturingOrder.product))
        .order_by(ManufacturingOrder.created_date.asc(), ManufacturingOrder.reference_code.asc())
        .all()
    )
    purchase_orders = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.product), joinedload(PurchaseOrder.supplier))
        .order_by(PurchaseOrder.issue_date.asc(), PurchaseOrder.reference_code.asc())
        .all()
    )
    sales_orders = (
        db.query(SalesOrder)
        .options(joinedload(SalesOrder.product), joinedload(SalesOrder.linked_mfg_order))
        .order_by(SalesOrder.created_at.asc())
        .all()
    )
    wholesale_prices = db.query(WholesalePrice).options(joinedload(WholesalePrice.product)).all()
    financial_transactions = db.query(FinancialTransaction).order_by(FinancialTransaction.created_at.asc()).all()
    events = db.query(Event).order_by(Event.timestamp.asc()).all()

    # Load metrics snapshots from file
    metrics_snapshots: list[Any] = []
    # Navigate from manufacturer/backend/app/api/routes (6 levels) to repository root, then to logs
    metrics_path = Path(__file__).parent.parent.parent.parent.parent.parent / "logs" / "metrics.jsonl"
    if metrics_path.exists():
        try:
            with metrics_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        metrics_snapshots.append(json.loads(line))
        except Exception:
            pass

    # Export retailer data
    retailer_data = None
    try:
        with httpx.Client(timeout=10.0) as client:
            retailer_response = client.get("http://localhost:8003/api/admin/export/state")
            if retailer_response.status_code == 200:
                retailer_data = retailer_response.json()
    except Exception:
        pass

    # Export provider data
    provider_data = None
    try:
        with httpx.Client(timeout=10.0) as client:
            provider_response = client.get("http://localhost:8001/api/admin/export/state")
            if provider_response.status_code == 200:
                provider_data = provider_response.json()
    except Exception:
        pass

    payload = json_ready(
        {
            "config": ConfigService(db).serialize_config(),
            "products": [serialize_product(product) for product in products],
            "bom_entries": [serialize_bom_entry(entry) for entry in bom_entries],
            "suppliers": [serialize_supplier(supplier) for supplier in suppliers],
            "inventory": inventory_service.get_inventory_snapshot(),
            "manufacturing_orders": [serialize_manufacturing_order(order) for order in manufacturing_orders],
            "purchase_orders": [serialize_purchase_order(order) for order in purchase_orders],
            "sales_orders": [serialize_sales_order(order) for order in sales_orders],
            "wholesale_prices": [serialize_wholesale_price(wp) for wp in wholesale_prices],
            "financial_transactions": [serialize_financial_transaction(txn) for txn in financial_transactions],
            "events": [serialize_event(event) for event in events],
            "metrics_snapshots": metrics_snapshots,
            "retailer_data": retailer_data,
            "provider_data": provider_data,
        }
    )

    return make_attachment_response(payload, "simulation_state.json")


@router.get("/export/inventory-only/")
def export_inventory(db: Session = Depends(get_db)):
    products = (
        db.query(Product)
        .filter(Product.type == ProductType.MATERIAL)
        .order_by(Product.name.asc())
        .all()
    )
    payload = json_ready(
        {
            "inventory": InventoryService(db).get_inventory_snapshot(),
            "products": [serialize_product(product) for product in products],
        }
    )
    return make_attachment_response(payload, "inventory_state.json")


@router.get("/export/events-only/")
def export_events(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.timestamp.asc()).all()
    payload = json_ready({"events": [serialize_event(event) for event in events]})
    return make_attachment_response(payload, "events_history.json")


def parse_date_value(value: Any, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid date for `{field_name}`: {value}") from exc
    raise ValueError(f"Expected ISO date string for `{field_name}`.")


def parse_datetime_value(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid datetime for `{field_name}`: {value}") from exc
    raise ValueError(f"Expected ISO datetime string for `{field_name}`.")


def parse_decimal_value(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:  # pragma: no cover - defensive conversion guard
        raise ValueError(f"Invalid decimal value for `{field_name}`: {value}") from exc


def parse_enum_value(enum_cls: type[Enum], value: Any, field_name: str) -> Enum:
    try:
        return enum_cls(value)
    except ValueError as exc:
        options = ", ".join(item.value for item in enum_cls)
        raise ValueError(f"Invalid value for `{field_name}`: {value}. Expected one of: {options}.") from exc


def expect_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"`{key}` must be a list in the imported state.")
    return value


def expect_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"`{key}` must be an object in the imported state.")
    return value


def ensure_required_sections(payload: dict[str, Any]) -> None:
    required_sections = [
        "config",
        "products",
        "bom_entries",
        "suppliers",
        "inventory",
        "manufacturing_orders",
        "purchase_orders",
        "sales_orders",
        "wholesale_prices",
        "financial_transactions",
        "events",
    ]
    missing = [section for section in required_sections if section not in payload]
    if missing:
        raise ValueError(f"Imported state is missing required sections: {', '.join(missing)}.")


def import_full_state_payload(db: Session, payload: dict[str, Any]) -> ImportResult:
    if not isinstance(payload, dict):
        raise ValueError("Imported state must be a JSON object.")

    ensure_required_sections(payload)

    config_payload = expect_object(payload, "config")
    products_payload = expect_list(payload, "products")
    bom_entries_payload = expect_list(payload, "bom_entries")
    suppliers_payload = expect_list(payload, "suppliers")
    inventory_payload = expect_list(payload, "inventory")
    manufacturing_orders_payload = expect_list(payload, "manufacturing_orders")
    purchase_orders_payload = expect_list(payload, "purchase_orders")
    sales_orders_payload = expect_list(payload, "sales_orders")
    wholesale_prices_payload = expect_list(payload, "wholesale_prices")
    financial_transactions_payload = expect_list(payload, "financial_transactions")
    events_payload = expect_list(payload, "events")
    metrics_snapshots = payload.get("metrics_snapshots", [])

    product_ids: set[str] = set()
    material_ids: set[str] = set()
    printer_ids: set[str] = set()

    for index, product in enumerate(products_payload):
        if not isinstance(product, dict):
            raise ValueError(f"`products[{index}]` must be an object.")
        product_id = product.get("id")
        if not product_id:
            raise ValueError(f"`products[{index}].id` is required.")
        if product_id in product_ids:
            raise ValueError(f"Duplicate product id found in imported state: {product_id}.")
        product_ids.add(product_id)

        product_type = parse_enum_value(ProductType, product.get("type"), f"products[{index}].type")
        if product_type == ProductType.MATERIAL:
            material_ids.add(product_id)
        else:
            printer_ids.add(product_id)

    try:
        db.query(Event).delete()
        db.query(FinancialTransaction).delete()
        db.query(SalesOrder).delete()
        db.query(WholesalePrice).delete()
        db.query(PurchaseOrder).delete()
        db.query(ManufacturingOrder).delete()
        db.query(Inventory).delete()
        db.query(Supplier).delete()
        db.query(BillOfMaterials).delete()
        db.query(Product).delete()
        db.query(SimulationConfig).delete()

        config = SimulationConfig(
            id=int(config_payload.get("id", 1)),
            warehouse_capacity=int(config_payload.get("warehouse_capacity", 2200)),
            daily_assembly_hours=float(config_payload.get("daily_assembly_hours", 8.0)),
            assembly_lines=int(config_payload.get("assembly_lines", 1)),
            workers_per_line=int(config_payload.get("workers_per_line", 1)),
            shift_hours=float(config_payload.get("shift_hours", 8.0)),
            demand_distribution_mean=float(config_payload.get("demand_distribution_mean", 5.0)),
            demand_distribution_variance=float(config_payload.get("demand_distribution_variance", 2.0)),
            internal_demand_enabled=bool(config_payload.get("internal_demand_enabled", False)),
            sim_date=parse_date_value(config_payload.get("sim_date"), "config.sim_date"),
            sim_day=int(config_payload.get("sim_day", 0)),
            cost_per_assembly_line=float(config_payload.get("cost_per_assembly_line", 50000.0)),
            cost_per_assembly_line_per_day=float(config_payload.get("cost_per_assembly_line_per_day", 100.0)),
            cost_per_worker_per_hour=float(config_payload.get("cost_per_worker_per_hour", 50.0)),
            max_workers_per_line=int(config_payload.get("max_workers_per_line", 10)),
            total_costs=float(config_payload.get("total_costs", 0.0)),
            total_revenue=float(config_payload.get("total_revenue", 0.0)),
            retailer_demand_enabled=bool(config_payload.get("retailer_demand_enabled", False)),
            retailer_demand_mean=float(config_payload.get("retailer_demand_mean", 8.0)),
            retailer_demand_variance=float(config_payload.get("retailer_demand_variance", 2.0)),
            retailer_demand_modifier=float(config_payload.get("retailer_demand_modifier", 1.0)),
            retailer_demand_base_price=float(config_payload.get("retailer_demand_base_price", 400.0)),
            provider_urls=config_payload.get("provider_urls"),
        )
        db.add(config)

        for index, product in enumerate(products_payload):
            db.add(
                Product(
                    id=product["id"],
                    name=str(product["name"]),
                    type=parse_enum_value(ProductType, product["type"], f"products[{index}].type"),
                    assembly_hours=float(product["assembly_hours"]) if product.get("assembly_hours") is not None else None,
                    created_at=parse_datetime_value(product["created_at"], f"products[{index}].created_at")
                    if product.get("created_at")
                    else datetime.utcnow(),
                )
            )

        for index, bom_entry in enumerate(bom_entries_payload):
            if bom_entry.get("finished_product_id") not in printer_ids:
                raise ValueError(
                    f"`bom_entries[{index}].finished_product_id` must reference an imported printer product."
                )
            if bom_entry.get("material_id") not in material_ids:
                raise ValueError(
                    f"`bom_entries[{index}].material_id` must reference an imported material product."
                )
            db.add(
                BillOfMaterials(
                    id=str(bom_entry["id"]),
                    finished_product_id=str(bom_entry["finished_product_id"]),
                    material_id=str(bom_entry["material_id"]),
                    quantity=parse_decimal_value(bom_entry["quantity"], f"bom_entries[{index}].quantity"),
                )
            )

        for index, supplier in enumerate(suppliers_payload):
            if supplier.get("product_id") not in material_ids:
                raise ValueError(f"`suppliers[{index}].product_id` must reference an imported material product.")
            db.add(
                Supplier(
                    id=str(supplier["id"]),
                    name=str(supplier["name"]),
                    product_id=str(supplier["product_id"]),
                    unit_cost=parse_decimal_value(supplier["unit_cost"], f"suppliers[{index}].unit_cost"),
                    lead_time_days=int(supplier["lead_time_days"]),
                    quantity_breaks=supplier.get("quantity_breaks"),
                    external_provider_url=supplier.get("external_provider_url"),
                    external_product_id=supplier.get("external_product_id"),
                )
            )

        for index, inventory_item in enumerate(inventory_payload):
            if inventory_item.get("product_id") not in material_ids:
                raise ValueError(f"`inventory[{index}].product_id` must reference an imported material product.")
            db.add(
                Inventory(
                    product_id=str(inventory_item["product_id"]),
                    quantity=parse_decimal_value(inventory_item["quantity"], f"inventory[{index}].quantity"),
                    last_updated=parse_datetime_value(inventory_item["last_updated"], f"inventory[{index}].last_updated")
                    if inventory_item.get("last_updated")
                    else datetime.utcnow(),
                )
            )

        for index, order in enumerate(manufacturing_orders_payload):
            if order.get("product_id") not in printer_ids:
                raise ValueError(
                    f"`manufacturing_orders[{index}].product_id` must reference an imported printer product."
                )
            db.add(
                ManufacturingOrder(
                    id=str(order["id"]),
                    reference_code=order.get("reference_code"),
                    product_id=str(order["product_id"]),
                    quantity=int(order["quantity"]),
                    status=parse_enum_value(OrderStatus, order["status"], f"manufacturing_orders[{index}].status"),
                    status_reason=order.get("status_reason"),
                    created_date=parse_date_value(order["created_date"], f"manufacturing_orders[{index}].created_date"),
                    released_date=parse_date_value(order["released_date"], f"manufacturing_orders[{index}].released_date")
                    if order.get("released_date")
                    else None,
                    completed_date=parse_date_value(order["completed_date"], f"manufacturing_orders[{index}].completed_date")
                    if order.get("completed_date")
                    else None,
                )
            )

        supplier_ids = {str(supplier["id"]) for supplier in suppliers_payload}
        manufacturing_order_ids = {str(order["id"]) for order in manufacturing_orders_payload}
        for index, purchase_order in enumerate(purchase_orders_payload):
            if purchase_order.get("supplier_id") not in supplier_ids:
                raise ValueError(
                    f"`purchase_orders[{index}].supplier_id` must reference an imported supplier."
                )
            if purchase_order.get("product_id") not in material_ids:
                raise ValueError(
                    f"`purchase_orders[{index}].product_id` must reference an imported material product."
                )
            db.add(
                PurchaseOrder(
                    id=str(purchase_order["id"]),
                    reference_code=purchase_order.get("reference_code"),
                    supplier_id=str(purchase_order["supplier_id"]),
                    product_id=str(purchase_order["product_id"]),
                    quantity=int(purchase_order["quantity"]),
                    issue_date=parse_date_value(purchase_order["issue_date"], f"purchase_orders[{index}].issue_date"),
                    expected_delivery=parse_date_value(
                        purchase_order["expected_delivery"],
                        f"purchase_orders[{index}].expected_delivery",
                    ),
                    actual_delivery=parse_date_value(
                        purchase_order["actual_delivery"],
                        f"purchase_orders[{index}].actual_delivery",
                    )
                    if purchase_order.get("actual_delivery")
                    else None,
                    status=parse_enum_value(
                        PurchaseOrderStatus,
                        purchase_order["status"],
                        f"purchase_orders[{index}].status",
                    ),
                    status_reason=purchase_order.get("status_reason"),
                    unit_cost=parse_decimal_value(purchase_order["unit_cost"], f"purchase_orders[{index}].unit_cost"),
                    external_order_id=purchase_order.get("external_order_id"),
                )
            )

        for index, event in enumerate(events_payload):
            db.add(
                Event(
                    id=str(event["id"]),
                    event_type=parse_enum_value(EventType, event["event_type"], f"events[{index}].event_type"),
                    sim_date=parse_date_value(event["sim_date"], f"events[{index}].sim_date"),
                    timestamp=parse_datetime_value(event["timestamp"], f"events[{index}].timestamp"),
                    details=event.get("details") or {},
                )
            )

        for index, sales_order in enumerate(sales_orders_payload):
            if sales_order.get("product_id") not in printer_ids:
                raise ValueError(
                    f"`sales_orders[{index}].product_id` must reference an imported printer product."
                )
            if sales_order.get("linked_mfg_order_id") is not None and sales_order.get("linked_mfg_order_id") not in manufacturing_order_ids:
                raise ValueError(
                    f"`sales_orders[{index}].linked_mfg_order_id` must reference an imported manufacturing order."
                )
            db.add(
                SalesOrder(
                    id=str(sales_order["id"]),
                    reference_code=sales_order.get("reference_code"),
                    retailer_name=str(sales_order["retailer_name"]),
                    product_id=str(sales_order["product_id"]),
                    quantity=int(sales_order["quantity"]),
                    status=parse_enum_value(
                        SalesOrderStatus,
                        sales_order["status"],
                        f"sales_orders[{index}].status",
                    ),
                    status_reason=sales_order.get("status_reason"),
                    unit_price=parse_decimal_value(sales_order["unit_price"], f"sales_orders[{index}].unit_price"),
                    total_price=parse_decimal_value(sales_order["total_price"], f"sales_orders[{index}].total_price"),
                    placed_day=int(sales_order["placed_day"]),
                    expected_ship_day=int(sales_order["expected_ship_day"]) if sales_order.get("expected_ship_day") is not None else None,
                    in_progress_day=int(sales_order["in_progress_day"]) if sales_order.get("in_progress_day") is not None else None,
                    shipped_day=int(sales_order["shipped_day"]) if sales_order.get("shipped_day") is not None else None,
                    delivered_day=int(sales_order["delivered_day"]) if sales_order.get("delivered_day") is not None else None,
                    linked_mfg_order_id=sales_order.get("linked_mfg_order_id"),
                    created_at=parse_datetime_value(sales_order["created_at"], f"sales_orders[{index}].created_at")
                    if sales_order.get("created_at")
                    else datetime.utcnow(),
                )
            )

        for index, wholesale_price in enumerate(wholesale_prices_payload):
            if wholesale_price.get("product_id") not in printer_ids:
                raise ValueError(
                    f"`wholesale_prices[{index}].product_id` must reference an imported printer product."
                )
            db.add(
                WholesalePrice(
                    product_id=str(wholesale_price["product_id"]),
                    price=parse_decimal_value(wholesale_price["price"], f"wholesale_prices[{index}].price"),
                    updated_at=parse_datetime_value(wholesale_price["updated_at"], f"wholesale_prices[{index}].updated_at")
                    if wholesale_price.get("updated_at")
                    else datetime.utcnow(),
                )
            )

        for index, transaction in enumerate(financial_transactions_payload):
            db.add(
                FinancialTransaction(
                    id=str(transaction["id"]),
                    transaction_type=parse_enum_value(
                        FinancialTransactionType,
                        transaction["transaction_type"],
                        f"financial_transactions[{index}].transaction_type",
                    ),
                    amount=parse_decimal_value(transaction["amount"], f"financial_transactions[{index}].amount"),
                    description=str(transaction["description"]),
                    sim_day=int(transaction["sim_day"]),
                    created_at=parse_datetime_value(transaction["created_at"], f"financial_transactions[{index}].created_at")
                    if transaction.get("created_at")
                    else datetime.utcnow(),
                )
            )

        db.commit()

        # Restore metrics snapshots if present
        if metrics_snapshots:
            try:
                # Navigate from manufacturer/backend/app/api/routes (6 levels) to repository root, then to logs
                metrics_path = Path(__file__).parent.parent.parent.parent.parent.parent / "logs" / "metrics.jsonl"
                metrics_path.parent.mkdir(exist_ok=True, parents=True)
                with metrics_path.open("w", encoding="utf-8") as f:
                    for snapshot in metrics_snapshots:
                        f.write(json.dumps(snapshot, default=str) + "\n")
            except Exception:
                pass

        # Restore retailer data if present
        retailer_data = payload.get("retailer_data")
        if retailer_data:
            try:
                with httpx.Client(timeout=10.0) as client:
                    client.post("http://localhost:8003/api/admin/import/state", json=retailer_data)
            except Exception:
                pass

        # Restore provider data if present
        provider_data = payload.get("provider_data")
        if provider_data:
            try:
                with httpx.Client(timeout=10.0) as client:
                    client.post("http://localhost:8001/api/admin/import/state", json=provider_data)
            except Exception:
                pass
    except Exception:
        db.rollback()
        raise

    return ImportResult(
        success=True,
        message=(
            "Imported full simulator state successfully: "
            f"{len(products_payload)} products, "
            f"{len(manufacturing_orders_payload)} manufacturing orders, "
            f"{len(purchase_orders_payload)} purchase orders, "
            f"{len(sales_orders_payload)} sales orders, "
            f"{len(wholesale_prices_payload)} wholesale prices, "
            f"{len(financial_transactions_payload)} financial transactions, "
            f"{len(events_payload)} events, "
            f"and {len(metrics_snapshots)} metric snapshots restored."
        ),
    )


@router.post("/import/full-state/")
async def import_full_state(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    try:
        return import_full_state_payload(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
