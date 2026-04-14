from sqlalchemy.orm import Session
from app.models.models import Supplier, PurchaseOrder, PurchaseOrderStatus, Product, Event, EventType, Inventory
from app.schemas.schemas import SupplierCreate, SupplierUpdate, PurchaseOrderCreate
from datetime import date, timedelta
from typing import List


class SupplierService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_suppliers(self) -> List[Supplier]:
        return self.db.query(Supplier).all()

    def get_supplier_by_id(self, supplier_id: str) -> Supplier:
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
        """Calculate unit cost based on quantity breaks"""
        if not supplier.quantity_breaks:
            return float(supplier.unit_cost)
        
        # Sort quantity breaks by quantity descending
        breaks = sorted(supplier.quantity_breaks, key=lambda x: x["qty"], reverse=True)
        
        for break_tier in breaks:
            if quantity >= break_tier["qty"]:
                return break_tier["price"]
        
        return float(supplier.unit_cost)


class PurchaseOrderService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_purchase_orders(self) -> List[PurchaseOrder]:
        return self.db.query(PurchaseOrder).all()

    def get_purchase_order_by_id(self, po_id: str) -> PurchaseOrder:
        return self.db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()

    def create_purchase_order(self, po: PurchaseOrderCreate, sim_date: date) -> PurchaseOrder:
        supplier = self.db.query(Supplier).filter(Supplier.id == po.supplier_id).first()
        if not supplier:
            raise ValueError("Supplier not found")
        
        # Calculate unit cost based on quantity
        unit_cost = SupplierService(self.db).calculate_unit_cost(supplier, po.quantity)
        
        # Calculate expected delivery date
        expected_delivery = sim_date + timedelta(days=supplier.lead_time_days)
        
        new_po = PurchaseOrder(
            supplier_id=po.supplier_id,
            product_id=po.product_id,
            quantity=po.quantity,
            issue_date=sim_date,
            expected_delivery=expected_delivery,
            unit_cost=unit_cost,
            status=PurchaseOrderStatus.PENDING
        )
        
        self.db.add(new_po)
        
        # Log event
        event = Event(
            event_type=EventType.PO_CREATED,
            sim_date=sim_date,
            details={
                "po_id": new_po.id,
                "supplier_id": po.supplier_id,
                "product_id": po.product_id,
                "quantity": po.quantity,
                "expected_delivery": expected_delivery.isoformat()
            }
        )
        self.db.add(event)
        
        self.db.commit()
        self.db.refresh(new_po)
        return new_po

    def process_deliveries(self, sim_date: date) -> List[dict]:
        """Process all purchase orders that are due for delivery"""
        due_pos = self.db.query(PurchaseOrder).filter(
            PurchaseOrder.status == PurchaseOrderStatus.PENDING,
            PurchaseOrder.expected_delivery <= sim_date
        ).all()
        
        results = []
        from app.services.inventory_service import InventoryService
        inventory_service = InventoryService(self.db)
        
        for po in due_pos:
            # Check warehouse capacity
            if not inventory_service.has_capacity_for(po.quantity):
                po.status = PurchaseOrderStatus.REJECTED
                self.db.commit()
                
                event = Event(
                    event_type=EventType.PO_REJECTED_CAPACITY,
                    sim_date=sim_date,
                    details={
                        "po_id": po.id,
                        "quantity": po.quantity,
                        "reason": "Warehouse capacity exceeded"
                    }
                )
                self.db.add(event)
                self.db.commit()
                
                results.append({"po_id": po.id, "status": "rejected", "reason": "Capacity exceeded"})
                continue
            
            # Deliver the order
            po.status = PurchaseOrderStatus.DELIVERED
            po.actual_delivery = sim_date
            
            # Update inventory
            inventory_service.update_inventory(po.product_id, po.quantity, "add")
            
            # Log event
            event = Event(
                event_type=EventType.PO_DELIVERED,
                sim_date=sim_date,
                details={
                    "po_id": po.id,
                    "product_id": po.product_id,
                    "quantity": po.quantity
                }
            )
            self.db.add(event)
            self.db.commit()
            
            results.append({"po_id": po.id, "status": "delivered"})
        
        return results
