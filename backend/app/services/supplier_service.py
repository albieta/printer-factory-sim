from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import List

from sqlalchemy.orm import Session

from app.models.models import Event, EventType, PurchaseOrder, PurchaseOrderStatus, Supplier
from app.schemas.schemas import PurchaseOrderCreate, SupplierCreate, SupplierUpdate
from app.services.presentation_service import serialize_purchase_order
from app.services.reference_service import next_reference_code


class SupplierService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_suppliers(self) -> List[Supplier]:
        return self.db.query(Supplier).all()

    def get_supplier_by_id(self, supplier_id: str) -> Supplier | None:
        return self.db.query(Supplier).filter(Supplier.id == supplier_id).first()

    def create_supplier(self, supplier: SupplierCreate) -> Supplier:
        new_supplier = Supplier(**supplier.model_dump())
        self.db.add(new_supplier)
        self.db.commit()
        self.db.refresh(new_supplier)
        return new_supplier

    def update_supplier(self, supplier_id: str, update: SupplierUpdate) -> Supplier:
        supplier = self.get_supplier_by_id(supplier_id)
        if not supplier:
            raise ValueError("Supplier not found")

        for key, value in update.model_dump(exclude_unset=True).items():
            setattr(supplier, key, value)

        self.db.commit()
        self.db.refresh(supplier)
        return supplier

    def delete_supplier(self, supplier_id: str) -> bool:
        supplier = self.get_supplier_by_id(supplier_id)
        if not supplier:
            return False

        self.db.delete(supplier)
        self.db.commit()
        return True

    def calculate_unit_cost(self, supplier: Supplier, quantity: int) -> float:
        if not supplier.quantity_breaks:
            return float(supplier.unit_cost)

        breaks = sorted(supplier.quantity_breaks, key=lambda item: item["qty"], reverse=True)
        for break_tier in breaks:
            if quantity >= break_tier["qty"]:
                return float(break_tier["price"])

        return float(supplier.unit_cost)

    def serialize_supplier(self, supplier: Supplier) -> dict:
        return {
            "id": supplier.id,
            "name": supplier.name,
            "product_id": supplier.product_id,
            "product_name": supplier.product.name if getattr(supplier, "product", None) else None,
            "unit_cost": float(supplier.unit_cost),
            "lead_time_days": supplier.lead_time_days,
            "quantity_breaks": supplier.quantity_breaks,
        }


class PurchaseOrderService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_purchase_orders(self) -> List[PurchaseOrder]:
        return self.db.query(PurchaseOrder).order_by(PurchaseOrder.issue_date.desc(), PurchaseOrder.reference_code.desc()).all()

    def get_purchase_order_by_id(self, po_id: str) -> PurchaseOrder | None:
        return self.db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()

    def create_purchase_order(self, po: PurchaseOrderCreate, sim_date: date) -> PurchaseOrder:
        supplier = self.db.query(Supplier).filter(Supplier.id == po.supplier_id).first()
        if not supplier:
            raise ValueError("Supplier not found")

        unit_cost = SupplierService(self.db).calculate_unit_cost(supplier, po.quantity)
        expected_delivery = sim_date + timedelta(days=supplier.lead_time_days)

        new_po = PurchaseOrder(
            supplier_id=po.supplier_id,
            product_id=po.product_id,
            quantity=po.quantity,
            issue_date=sim_date,
            expected_delivery=expected_delivery,
            unit_cost=unit_cost,
            status=PurchaseOrderStatus.PENDING,
            status_reason=None,
        )
        new_po.reference_code = next_reference_code(self.db, PurchaseOrder, "PO", "issue_date", sim_date)

        self.db.add(new_po)
        self.db.flush()

        event = Event(
            event_type=EventType.PO_CREATED,
            sim_date=sim_date,
            details={
                "po_id": new_po.id,
                "reference_code": new_po.reference_code,
                "supplier_id": po.supplier_id,
                "product_id": po.product_id,
                "quantity": po.quantity,
                "unit_cost": unit_cost,
                "total_cost": float(po.quantity * unit_cost),
                "expected_delivery": expected_delivery.isoformat(),
            },
        )
        self.db.add(event)

        self.db.commit()
        self.db.refresh(new_po)
        return new_po

    def process_deliveries(self, sim_date: date) -> List[dict]:
        due_pos = self.db.query(PurchaseOrder).filter(
            PurchaseOrder.status == PurchaseOrderStatus.PENDING,
            PurchaseOrder.expected_delivery <= sim_date,
        ).all()

        results = []
        from app.services.inventory_service import InventoryService

        inventory_service = InventoryService(self.db)
        delivered_any = False

        for po in due_pos:
            if not inventory_service.has_capacity_for(Decimal(po.quantity)):
                po.status = PurchaseOrderStatus.REJECTED
                po.status_reason = "Receipt rejected because the warehouse would exceed configured capacity on delivery."
                self.db.commit()

                event = Event(
                    event_type=EventType.PO_REJECTED_CAPACITY,
                    sim_date=sim_date,
                    details={
                        "po_id": po.id,
                        "reference_code": po.reference_code,
                        "quantity": po.quantity,
                        "reason": po.status_reason,
                    },
                )
                self.db.add(event)
                self.db.commit()

                results.append({"po_id": po.id, "status": "rejected", "reason": po.status_reason})
                continue

            po.status = PurchaseOrderStatus.DELIVERED
            po.status_reason = None
            po.actual_delivery = sim_date

            inventory_service.update_inventory(po.product_id, Decimal(po.quantity), "add")

            event = Event(
                event_type=EventType.PO_DELIVERED,
                sim_date=sim_date,
                details={
                    "po_id": po.id,
                    "reference_code": po.reference_code,
                    "product_id": po.product_id,
                    "quantity": po.quantity,
                },
            )
            self.db.add(event)
            self.db.commit()

            delivered_any = True
            results.append({"po_id": po.id, "status": "delivered"})

        if delivered_any:
            from app.services.order_service import OrderService

            OrderService(self.db).recheck_blocked_orders(sim_date)

        return results

    def serialize_purchase_order(self, order: PurchaseOrder) -> dict:
        return serialize_purchase_order(order)
