from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Any, List, Optional, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import (
    BillOfMaterials,
    Event,
    EventType,
    Inventory,
    ManufacturingOrder,
    OrderStatus,
    Product,
    ProductType,
    PurchaseOrder,
    PurchaseOrderStatus,
    SimulationConfig,
)


class InventoryService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_inventory(self) -> List[Inventory]:
        return self.db.query(Inventory).all()

    def get_inventory_snapshot(self) -> list[dict[str, Any]]:
        accepted_order_demand = self.get_accepted_order_material_demand()
        pending_inbound_by_material = self.get_pending_inbound_material_quantity()
        inventory_by_product = {item.product_id: item for item in self.get_all_inventory()}
        materials = (
            self.db.query(Product)
            .filter(Product.type == ProductType.MATERIAL)
            .order_by(Product.name.asc())
            .all()
        )

        snapshot: list[dict[str, Any]] = []
        for material in materials:
            inventory = inventory_by_product.get(material.id)
            if inventory:
                snapshot.append(
                    self.serialize_inventory_level(
                        inventory,
                        accepted_order_demand.get(material.id, 0.0),
                        pending_inbound_by_material.get(material.id, 0.0),
                    )
                )
                continue

            snapshot.append(
                {
                    "product_id": material.id,
                    "product_name": material.name,
                    "quantity": 0.0,
                    "last_updated": None,
                    "accepted_order_demand": accepted_order_demand.get(material.id, 0.0),
                    "pending_inbound_quantity": pending_inbound_by_material.get(material.id, 0.0),
                }
            )

        return snapshot

    def get_inventory_by_product(self, product_id: str) -> Inventory:
        inventory = self.db.query(Inventory).filter(Inventory.product_id == product_id).first()
        if not inventory:
            inventory = Inventory(product_id=product_id, quantity=0)
            self.db.add(inventory)
            self.db.commit()
            self.db.refresh(inventory)
        return inventory

    def update_inventory(self, product_id: str, quantity_change: Decimal, operation: str = "add") -> Inventory:
        inventory = self.get_inventory_by_product(product_id)

        if operation == "add":
            inventory.quantity += quantity_change
        elif operation == "subtract":
            if inventory.quantity < quantity_change:
                raise ValueError(f"Insufficient inventory for product {product_id}")
            inventory.quantity -= quantity_change
        elif operation == "set":
            inventory.quantity = quantity_change
        else:
            raise ValueError(f"Invalid operation: {operation}")

        inventory.last_updated = datetime.utcnow()
        self.db.commit()
        self.db.refresh(inventory)
        return inventory

    def check_inventory_availability(self, product_id: str, required_quantity: Decimal) -> bool:
        inventory = self.get_inventory_by_product(product_id)
        return inventory.quantity >= required_quantity

    def get_total_inventory_count(self) -> Decimal:
        raw = cast(Optional[Decimal], self.db.query(func.sum(Inventory.quantity)).scalar())
        return raw if raw is not None else Decimal(0)

    def get_capacity_info(self) -> dict[str, Any]:
        from app.services.config_service import ConfigService
        config_service = ConfigService(self.db)
        config = config_service.get_config()
        total_inventory = self.get_total_inventory_count()
        warehouse_capacity = config.warehouse_capacity if config else 8400
        available_capacity = float(warehouse_capacity - total_inventory)

        return {
            "warehouse_capacity": warehouse_capacity,
            "current_usage": float(total_inventory),
            "available_capacity": available_capacity,
            "usage_percentage": float((total_inventory / warehouse_capacity) * 100) if warehouse_capacity > 0 else 0,
            "assembly_lines": config.assembly_lines,
            "workers_per_line": config.workers_per_line,
            "daily_assembly_hours": config.daily_assembly_hours,
        }

    def has_capacity_for(self, quantity: Decimal) -> bool:
        config = self.db.query(SimulationConfig).first()
        total_inventory = self.get_total_inventory_count()
        warehouse_capacity = config.warehouse_capacity if config else 8400
        return (total_inventory + quantity) <= warehouse_capacity

    def get_accepted_order_material_demand(self) -> dict[str, float]:
        accepted_orders = (
            self.db.query(ManufacturingOrder)
            .filter(ManufacturingOrder.status.in_((OrderStatus.RELEASED, OrderStatus.BLOCKED)))
            .all()
        )

        if not accepted_orders:
            return {}

        demand_by_material: dict[str, Decimal] = {}
        bom_entries = self.db.query(BillOfMaterials).all()
        bom_by_product: dict[str, list[BillOfMaterials]] = {}
        for bom in bom_entries:
            bom_by_product.setdefault(bom.finished_product_id, []).append(bom)

        for order in accepted_orders:
            for bom in bom_by_product.get(order.product_id, []):
                required_qty = Decimal(str(order.quantity)) * bom.quantity
                demand_by_material[bom.material_id] = demand_by_material.get(bom.material_id, Decimal(0)) + required_qty

        return {material_id: float(quantity) for material_id, quantity in demand_by_material.items()}

    def get_pending_inbound_material_quantity(self) -> dict[str, float]:
        pending_purchase_orders = (
            self.db.query(PurchaseOrder)
            .filter(PurchaseOrder.status == PurchaseOrderStatus.PENDING)
            .all()
        )

        inbound_by_material: dict[str, int] = {}
        for purchase_order in pending_purchase_orders:
            inbound_by_material[purchase_order.product_id] = inbound_by_material.get(purchase_order.product_id, 0) + purchase_order.quantity

        return {material_id: float(quantity) for material_id, quantity in inbound_by_material.items()}

    def serialize_inventory_level(
        self,
        item: Inventory,
        accepted_order_demand: float = 0.0,
        pending_inbound_quantity: float = 0.0,
    ) -> dict[str, Any]:
        product = self.db.query(Product).filter(Product.id == item.product_id).first()
        return {
            "product_id": item.product_id,
            "product_name": product.name if product else None,
            "quantity": float(item.quantity),
            "last_updated": item.last_updated,
            "accepted_order_demand": accepted_order_demand,
            "pending_inbound_quantity": pending_inbound_quantity,
        }

    def log_adjustment(
        self, product_id: str, quantity: float, adjustment_type: str, reason: str, sim_date: date
    ) -> None:
        event_type = EventType.MATERIAL_TRASHED if adjustment_type == "TRASHED" else EventType.MATERIAL_ADJUSTED
        product = self.db.query(Product).filter(Product.id == product_id).first()
        event = Event(
            event_type=event_type,
            sim_date=sim_date,
            details={
                "product_id": product_id,
                "product_name": product.name if product else None,
                "quantity": quantity,
                "reason": reason,
                "adjustment_type": adjustment_type,
            },
        )
        self.db.add(event)
        self.db.commit()

    def get_adjustment_logs(self) -> list[dict[str, Any]]:
        events = (
            self.db.query(Event)
            .filter(Event.event_type.in_([EventType.MATERIAL_TRASHED, EventType.MATERIAL_ADJUSTED]))
            .order_by(Event.sim_date.desc(), Event.timestamp.desc())
            .all()
        )
        result = []
        for event in events:
            details = event.details or {}
            result.append(
                {
                    "id": event.id,
                    "product_id": details.get("product_id"),
                    "product_name": details.get("product_name"),
                    "adjustment_type": details.get("adjustment_type"),
                    "quantity": details.get("quantity"),
                    "reason": details.get("reason"),
                    "sim_date": event.sim_date,
                    "timestamp": event.timestamp,
                }
            )
        return result
