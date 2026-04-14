from sqlalchemy.orm import Session
from app.models.models import ManufacturingOrder, Product, BillOfMaterials, Inventory, Event, EventType, OrderStatus
from app.schemas.schemas import ReleaseRequest, BatchReleaseResponse, BOMRequirements
from datetime import date
from decimal import Decimal
from typing import List, Tuple


class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_orders(self, status: OrderStatus = None) -> List[ManufacturingOrder]:
        query = self.db.query(ManufacturingOrder)
        if status:
            query = query.filter(ManufacturingOrder.status == status)
        return query.all()

    def get_order_by_id(self, order_id: str) -> ManufacturingOrder:
        return self.db.query(ManufacturingOrder).filter(ManufacturingOrder.id == order_id).first()

    def get_bom_requirements(self, product_id: str) -> List[Tuple]:
        return (
            self.db.query(BillOfMaterials)
            .filter(BillOfMaterials.finished_product_id == product_id)
            .all()
        )

    def check_materials_availability(self, product_id: str, quantity: int) -> Tuple[bool, List[dict]]:
        bom_entries = self.get_bom_requirements(product_id)
        unavailable = []
        
        for bom in bom_entries:
            required_qty = bom.quantity * quantity
            inventory = self.db.query(Inventory).filter(Inventory.product_id == bom.material_id).first()
            available_qty = inventory.quantity if inventory else Decimal(0)
            
            if available_qty < required_qty:
                material = self.db.query(Product).filter(Product.id == bom.material_id).first()
                unavailable.append({
                    "material_id": bom.material_id,
                    "material_name": material.name if material else "Unknown",
                    "required": float(required_qty),
                    "available": float(available_qty)
                })
        
        return len(unavailable) == 0, unavailable

    def release_order(self, order_id: str, sim_date: date) -> dict:
        order = self.get_order_by_id(order_id)
        if not order:
            return {"success": False, "error": "Order not found"}
        
        if order.status != OrderStatus.PENDING:
            return {"success": False, "error": f"Order is {order.status}, not PENDING"}
        
        # Check materials availability
        available, unavailable = self.check_materials_availability(order.product_id, order.quantity)
        
        if not available:
            order.status = OrderStatus.BLOCKED
            self.db.commit()
            
            # Log event
            event = Event(
                event_type=EventType.ORDER_BLOCKED_MATERIALS,
                sim_date=sim_date,
                details={
                    "order_id": order_id,
                    "product_id": order.product_id,
                    "unavailable_materials": unavailable
                }
            )
            self.db.add(event)
            self.db.commit()
            
            return {"success": False, "error": "Insufficient materials", "unavailable": unavailable}
        
        # Release the order
        order.status = OrderStatus.RELEASED
        order.released_date = sim_date
        self.db.commit()
        
        # Log event
        event = Event(
            event_type=EventType.ORDER_RELEASED,
            sim_date=sim_date,
            details={"order_id": order_id, "product_id": order.product_id, "quantity": order.quantity}
        )
        self.db.add(event)
        self.db.commit()
        
        return {"success": True}

    def batch_release_orders(self, request: ReleaseRequest, sim_date: date) -> BatchReleaseResponse:
        response = BatchReleaseResponse(successful=[], failed=[])
        
        for order_id in request.order_ids:
            result = self.release_order(order_id, sim_date)
            if result["success"]:
                response.successful.append(order_id)
            else:
                response.failed.append({"order_id": order_id, "reason": result.get("error", "Unknown")})
        
        return response

    def create_order(self, product_id: str, quantity: int, sim_date: date) -> ManufacturingOrder:
        order = ManufacturingOrder(
            product_id=product_id,
            quantity=quantity,
            status=OrderStatus.PENDING,
            created_date=sim_date
        )
        self.db.add(order)
        
        # Log event
        event = Event(
            event_type=EventType.ORDER_CREATED,
            sim_date=sim_date,
            details={"order_id": order.id, "product_id": product_id, "quantity": quantity}
        )
        self.db.add(event)
        
        self.db.commit()
        self.db.refresh(order)
        return order
