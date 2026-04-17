from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Inventory, Product, SimulationConfig


class InventoryService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_inventory(self) -> List[Inventory]:
        return self.db.query(Inventory).all()

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
        result = self.db.query(func.sum(Inventory.quantity)).scalar()
        return result if result else Decimal(0)

    def get_capacity_info(self) -> dict:
        config = self.db.query(SimulationConfig).first()
        total_inventory = self.get_total_inventory_count()
        warehouse_capacity = config.warehouse_capacity if config else 2200
        available_capacity = float(warehouse_capacity - total_inventory)

        return {
            "warehouse_capacity": warehouse_capacity,
            "current_usage": float(total_inventory),
            "available_capacity": available_capacity,
            "usage_percentage": float((total_inventory / warehouse_capacity) * 100) if warehouse_capacity > 0 else 0,
        }

    def has_capacity_for(self, quantity: Decimal) -> bool:
        config = self.db.query(SimulationConfig).first()
        total_inventory = self.get_total_inventory_count()
        warehouse_capacity = config.warehouse_capacity if config else 2200
        return (total_inventory + quantity) <= warehouse_capacity

    def serialize_inventory_level(self, item: Inventory) -> dict:
        product = self.db.query(Product).filter(Product.id == item.product_id).first()
        return {
            "product_id": item.product_id,
            "product_name": product.name if product else None,
            "quantity": float(item.quantity),
            "last_updated": item.last_updated,
        }
