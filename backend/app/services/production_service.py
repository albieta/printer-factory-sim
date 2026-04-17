from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models.models import BillOfMaterials, Event, EventType, Inventory, ManufacturingOrder, OrderStatus, Product
from app.services.config_service import ConfigService


class ProductionService:
    def __init__(self, db: Session):
        self.db = db
        self.config_service = ConfigService(db)

    def get_available_assembly_hours(self, sim_date: date) -> float:
        return self.config_service.get_daily_assembly_hours()

    def get_assembly_hours_for_product(self, product_id: str) -> float:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        return float(product.assembly_hours) if product and product.assembly_hours else 0.0

    def execute_production(self, sim_date: date) -> List[dict]:
        released_orders = self.db.query(ManufacturingOrder).filter(ManufacturingOrder.status == OrderStatus.RELEASED).order_by(ManufacturingOrder.released_date, ManufacturingOrder.reference_code).all()
        available_hours = self.get_available_assembly_hours(sim_date)
        results: list[dict] = []

        for order in released_orders:
            if available_hours <= 0:
                event = Event(
                    event_type=EventType.PRODUCTION_BLOCKED_CAPACITY,
                    sim_date=sim_date,
                    details={
                        "order_id": order.id,
                        "reference_code": order.reference_code,
                        "remaining_capacity": 0,
                    },
                )
                self.db.add(event)
                self.db.commit()
                results.append({"order_id": order.id, "status": "blocked", "reason": "No assembly hours remaining"})
                break

            produced, hours_used = self.produce_order(order, available_hours, sim_date)
            if produced:
                available_hours -= hours_used
                results.append({"order_id": order.id, "status": "completed", "hours_used": hours_used})
            else:
                results.append({"order_id": order.id, "status": "blocked", "reason": "Insufficient materials or hours"})

        return results

    def produce_order(self, order: ManufacturingOrder, available_hours: float, sim_date: date) -> Tuple[bool, float]:
        product = self.db.query(Product).filter(Product.id == order.product_id).first()
        if not product:
            return False, 0

        required_hours = order.quantity * float(product.assembly_hours or 0)
        if required_hours > available_hours:
            return False, 0

        bom_entries = self.db.query(BillOfMaterials).filter(BillOfMaterials.finished_product_id == order.product_id).all()
        for bom in bom_entries:
            required_qty = bom.quantity * order.quantity
            inventory = self.db.query(Inventory).filter(Inventory.product_id == bom.material_id).first()
            available_qty = inventory.quantity if inventory else Decimal(0)
            if available_qty < required_qty:
                return False, 0

        for bom in bom_entries:
            required_qty = bom.quantity * order.quantity
            inventory = self.db.query(Inventory).filter(Inventory.product_id == bom.material_id).first()
            inventory.quantity -= required_qty
            inventory.last_updated = sim_date

            event = Event(
                event_type=EventType.MATERIAL_CONSUMED,
                sim_date=sim_date,
                details={
                    "order_id": order.id,
                    "reference_code": order.reference_code,
                    "material_id": bom.material_id,
                    "quantity_consumed": float(required_qty),
                },
            )
            self.db.add(event)

        order.status = OrderStatus.COMPLETED
        order.status_reason = None
        order.completed_date = sim_date

        event = Event(
            event_type=EventType.ORDER_COMPLETED,
            sim_date=sim_date,
            details={
                "order_id": order.id,
                "reference_code": order.reference_code,
                "product_id": order.product_id,
                "quantity": order.quantity,
                "hours_used": required_hours,
            },
        )
        self.db.add(event)

        self.db.commit()
        return True, required_hours
