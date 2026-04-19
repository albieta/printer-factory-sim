from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models.models import BillOfMaterials, Event, EventType, ManufacturingOrder, OrderStatus, Product, Inventory
from app.schemas.schemas import BatchReleaseResponse, ReleaseRequest
from app.services.presentation_service import serialize_manufacturing_order
from app.services.reference_service import next_reference_code


class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_orders(self, status: OrderStatus | None = None) -> List[ManufacturingOrder]:
        query = self.db.query(ManufacturingOrder).order_by(ManufacturingOrder.created_date.desc(), ManufacturingOrder.reference_code.desc())
        if status:
            query = query.filter(ManufacturingOrder.status == status)
        return query.all()

    def get_order_by_id(self, order_id: str) -> ManufacturingOrder | None:
        return self.db.query(ManufacturingOrder).filter(ManufacturingOrder.id == order_id).first()

    def get_bom_requirements(self, product_id: str) -> List[BillOfMaterials]:
        return self.db.query(BillOfMaterials).filter(BillOfMaterials.finished_product_id == product_id).all()

    def check_materials_availability(self, product_id: str, quantity: int) -> Tuple[bool, List[dict]]:
        bom_entries = self.get_bom_requirements(product_id)
        unavailable: list[dict] = []

        for bom in bom_entries:
            required_qty = bom.quantity * quantity
            inventory = self.db.query(Inventory).filter(Inventory.product_id == bom.material_id).first()
            available_qty = inventory.quantity if inventory else Decimal(0)

            if available_qty < required_qty:
                material = self.db.query(Product).filter(Product.id == bom.material_id).first()
                unavailable.append(
                    {
                        "material_id": bom.material_id,
                        "material_name": material.name if material else "Unknown",
                        "required": float(required_qty),
                        "available": float(available_qty),
                        "shortfall": float(required_qty - available_qty),
                    }
                )

        return len(unavailable) == 0, unavailable

    def build_blocked_reason(self, unavailable: List[dict]) -> str:
        if not unavailable:
            return "Release blocked because one or more required materials are unavailable."
        names = ", ".join(item["material_name"] for item in unavailable[:3])
        suffix = "" if len(unavailable) <= 3 else ", and others"
        return f"Release blocked by missing material stock: {names}{suffix}."

    def _record_event(self, event_type: EventType, sim_date: date, details: dict) -> None:
        self.db.add(
            Event(
                event_type=event_type,
                sim_date=sim_date,
                details=details,
            )
        )
        self.db.commit()

    def _build_order_event_details(self, order: ManufacturingOrder, extras: dict | None = None) -> dict:
        details = {
            "order_id": order.id,
            "reference_code": order.reference_code,
            "product_id": order.product_id,
            "product_name": order.product.name if getattr(order, "product", None) else None,
            "quantity": order.quantity,
        }
        if extras:
            details.update(extras)
        return details

    def release_order(self, order_id: str, sim_date: date) -> dict:
        order = self.get_order_by_id(order_id)
        if not order:
            return {"success": False, "error": "Order not found"}

        if order.status != OrderStatus.PENDING:
            return {"success": False, "error": f"Order is {order.status.value}, not PENDING"}

        available, unavailable = self.check_materials_availability(order.product_id, order.quantity)
        if not available:
            order.status = OrderStatus.BLOCKED
            order.status_reason = self.build_blocked_reason(unavailable)
            self.db.commit()
            self._record_event(
                EventType.ORDER_BLOCKED_MATERIALS,
                sim_date,
                self._build_order_event_details(
                    order,
                    {
                        "unavailable_materials": unavailable,
                        "reason": order.status_reason,
                    },
                ),
            )

            return {"success": False, "error": "Insufficient materials", "unavailable": unavailable, "reason": order.status_reason}

        order.status = OrderStatus.RELEASED
        order.status_reason = None
        order.released_date = sim_date
        self.db.commit()
        self._record_event(EventType.ORDER_RELEASED, sim_date, self._build_order_event_details(order))

        return {"success": True}

    def batch_release_orders(self, request: ReleaseRequest, sim_date: date) -> BatchReleaseResponse:
        response = BatchReleaseResponse(successful=[], failed=[])

        for order_id in request.order_ids:
            result = self.release_order(order_id, sim_date)
            if result["success"]:
                response.successful.append(order_id)
            else:
                response.failed.append(
                    {
                        "order_id": order_id,
                        "reason": result.get("reason") or result.get("error", "Unknown"),
                    }
                )

        return response

    def reject_order(self, order_id: str, sim_date: date) -> dict:
        order = self.get_order_by_id(order_id)
        if not order:
            return {"success": False, "error": "Order not found"}

        if order.status != OrderStatus.PENDING:
            return {"success": False, "error": f"Order is {order.status.value}, not PENDING"}

        order.status = OrderStatus.REJECTED
        order.status_reason = "Rejected during planner review."
        self.db.commit()
        self._record_event(
            EventType.ORDER_REJECTED,
            sim_date,
            self._build_order_event_details(order, {"reason": order.status_reason}),
        )
        return {"success": True}

    def batch_reject_orders(self, request: ReleaseRequest, sim_date: date) -> BatchReleaseResponse:
        response = BatchReleaseResponse(successful=[], failed=[])

        for order_id in request.order_ids:
            result = self.reject_order(order_id, sim_date)
            if result["success"]:
                response.successful.append(order_id)
            else:
                response.failed.append(
                    {
                        "order_id": order_id,
                        "reason": result.get("reason") or result.get("error", "Unknown"),
                    }
                )

        return response

    def recheck_blocked_orders(self, sim_date: date) -> list[str]:
        blocked_orders = (
            self.db.query(ManufacturingOrder)
            .filter(ManufacturingOrder.status == OrderStatus.BLOCKED)
            .order_by(ManufacturingOrder.created_date, ManufacturingOrder.reference_code)
            .all()
        )
        unblocked: list[str] = []

        for order in blocked_orders:
            available, unavailable = self.check_materials_availability(order.product_id, order.quantity)
            if not available:
                order.status_reason = self.build_blocked_reason(unavailable)
                self.db.commit()
                continue

            order.status = OrderStatus.RELEASED
            order.status_reason = None
            order.released_date = sim_date
            self.db.commit()
            self._record_event(
                EventType.ORDER_UNBLOCKED_MATERIALS,
                sim_date,
                self._build_order_event_details(order, {"reason": "Materials became available and the order returned to assembly."}),
            )
            unblocked.append(order.id)

        return unblocked

    def create_order(self, product_id: str, quantity: int, sim_date: date) -> ManufacturingOrder:
        order = ManufacturingOrder(
            product_id=product_id,
            quantity=quantity,
            status=OrderStatus.PENDING,
            created_date=sim_date,
            status_reason=None,
        )
        order.reference_code = next_reference_code(self.db, ManufacturingOrder, "MO", "created_date", sim_date)
        self.db.add(order)
        self.db.flush()

        event = Event(
            event_type=EventType.ORDER_CREATED,
            sim_date=sim_date,
            details={
                "order_id": order.id,
                "reference_code": order.reference_code,
                "product_id": product_id,
                "quantity": quantity,
            },
        )
        self.db.add(event)

        self.db.commit()
        self.db.refresh(order)
        return order

    def serialize_order(self, order: ManufacturingOrder) -> dict:
        return serialize_manufacturing_order(order)
