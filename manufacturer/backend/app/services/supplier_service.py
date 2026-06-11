from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, List

import httpx
from sqlalchemy.orm import Session

from app.models.models import Event, EventType, Inventory, PurchaseOrder, PurchaseOrderStatus, Supplier
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

    def serialize_supplier(self, supplier: Supplier) -> dict[str, Any]:
        return {
            "id": supplier.id,
            "name": supplier.name,
            "product_id": supplier.product_id,
            "product_name": supplier.product.name if getattr(supplier, "product", None) else None,
            "unit_cost": float(supplier.unit_cost),
            "lead_time_days": supplier.lead_time_days,
            "quantity_breaks": supplier.quantity_breaks,
            "external_provider_url": supplier.external_provider_url,
            "external_product_id": supplier.external_product_id,
        }


class PurchaseOrderService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_purchase_orders(self) -> List[PurchaseOrder]:
        return self.db.query(PurchaseOrder).order_by(PurchaseOrder.issue_date.desc(), PurchaseOrder.reference_code.desc()).all()

    def get_purchase_order_by_id(self, po_id: str) -> PurchaseOrder | None:
        return self.db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()

    def _provider_url(self, supplier: Supplier) -> str | None:
        return supplier.external_provider_url.rstrip("/") if supplier.external_provider_url else None

    def _create_external_order(self, supplier: Supplier, quantity: int) -> dict[str, Any] | None:
        provider_url = self._provider_url(supplier)
        if provider_url is None:
            return None
        if supplier.external_product_id is None:
            raise ValueError(f"Supplier {supplier.name!r} is missing external_product_id")

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{provider_url}/api/orders",
                    json={
                        "buyer": "manufacturer",
                        "product_id": supplier.external_product_id,
                        "quantity": quantity,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Provider rejected purchase order: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Provider purchase-order request failed: {exc}") from exc

        payload = response.json()
        order_payload = payload.get("order")
        if not isinstance(order_payload, dict):
            raise RuntimeError("Provider response did not include an order object")
        return order_payload

    def _get_external_order(self, supplier: Supplier, external_order_id: int) -> dict[str, Any]:
        provider_url = self._provider_url(supplier)
        if provider_url is None:
            raise ValueError("Purchase order is not connected to an external provider")

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{provider_url}/api/orders/{external_order_id}")
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Provider order poll failed: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Provider order poll failed: {exc}") from exc

        payload = response.json()
        order_payload = payload.get("order")
        if not isinstance(order_payload, dict):
            raise RuntimeError("Provider response did not include an order object")
        return order_payload

    def create_purchase_order(self, po: PurchaseOrderCreate, sim_date: date) -> PurchaseOrder:
        supplier = self.db.query(Supplier).filter(Supplier.id == po.supplier_id).first()
        if not supplier:
            raise ValueError("Supplier not found")

        external_order = self._create_external_order(supplier, po.quantity)
        unit_cost = SupplierService(self.db).calculate_unit_cost(supplier, po.quantity)
        if external_order is not None:
            unit_cost = float(external_order["unit_price"])
        expected_delivery = sim_date + timedelta(days=supplier.lead_time_days)
        if external_order is not None:
            placed_day = int(external_order.get("placed_day", 0))
            expected_day = int(external_order.get("expected_delivery_day", placed_day + supplier.lead_time_days))
            expected_delivery = sim_date + timedelta(days=max(1, expected_day - placed_day))
        external_status = str(external_order.get("status")) if external_order is not None else None

        new_po = PurchaseOrder(
            supplier_id=po.supplier_id,
            product_id=po.product_id,
            quantity=po.quantity,
            issue_date=sim_date,
            expected_delivery=expected_delivery,
            unit_cost=unit_cost,
            status=PurchaseOrderStatus.REJECTED if external_status == "REJECTED" else PurchaseOrderStatus.PENDING,
            status_reason=external_order.get("status_reason") if external_order is not None else None,
            external_order_id=external_order.get("id") if external_order is not None else None,
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
                "external_provider_url": supplier.external_provider_url,
                "external_order_id": new_po.external_order_id,
            },
        )
        self.db.add(event)
        if new_po.status == PurchaseOrderStatus.REJECTED:
            self.db.add(
                Event(
                    event_type=EventType.PO_REJECTED,
                    sim_date=sim_date,
                    details={
                        "po_id": new_po.id,
                        "reference_code": new_po.reference_code,
                        "external_order_id": new_po.external_order_id,
                        "reason": new_po.status_reason,
                    },
                )
            )

        self.db.commit()
        self.db.refresh(new_po)
        return new_po

    def process_deliveries(self, sim_date: date) -> list[dict[str, Any]]:
        due_pos = self.db.query(PurchaseOrder).join(Supplier).filter(
            PurchaseOrder.status == PurchaseOrderStatus.PENDING,
            PurchaseOrder.expected_delivery <= sim_date,
            Supplier.external_provider_url.is_(None),
        ).all()
        external_pos = self.db.query(PurchaseOrder).join(Supplier).filter(
            PurchaseOrder.status == PurchaseOrderStatus.PENDING,
            Supplier.external_provider_url.is_not(None),
            PurchaseOrder.external_order_id.is_not(None),
        ).all()

        results = []
        from app.services.inventory_service import InventoryService

        inventory_service = InventoryService(self.db)
        delivered_any = False

        # Sort deliveries: lowest current stock first so critical materials always
        # get warehouse space before oversupplied ones can fill it.
        def _current_stock(po: PurchaseOrder) -> float:
            inv = self.db.query(Inventory).filter(
                Inventory.product_id == po.product_id
            ).first()
            return float(inv.quantity) if inv and inv.quantity else 0.0

        all_pos = sorted([*due_pos, *external_pos], key=_current_stock)

        for po in all_pos:
            if po.supplier.external_provider_url and po.external_order_id is not None:
                external_order = self._get_external_order(po.supplier, po.external_order_id)
                external_status = str(external_order.get("status"))
                if external_status == "REJECTED":
                    po.status = PurchaseOrderStatus.REJECTED
                    po.status_reason = external_order.get("status_reason") or "Provider rejected the external order."
                    self.db.add(
                        Event(
                            event_type=EventType.PO_REJECTED,
                            sim_date=sim_date,
                            details={
                                "po_id": po.id,
                                "reference_code": po.reference_code,
                                "external_order_id": po.external_order_id,
                                "reason": po.status_reason,
                            },
                        )
                    )
                    self.db.commit()
                    results.append({"po_id": po.id, "status": "rejected", "reason": po.status_reason})
                    continue
                if external_status != "DELIVERED":
                    results.append({"po_id": po.id, "status": "in_flight", "provider_status": external_status})
                    continue

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

            if po.unit_cost and float(po.unit_cost) > 0:
                from app.models.models import SimulationConfig as SimConf
                from app.services.financial_service import FinancialService
                sim_day = self.db.query(SimConf).one().sim_day
                cost = float(po.unit_cost) * po.quantity
                product_label = po.product.name if po.product else str(po.product_id)
                FinancialService(self.db).record_materials_purchased(
                    sim_day, cost,
                    f"PO {po.reference_code}: {po.quantity}× {product_label}"
                )

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

    def serialize_purchase_order(self, order: PurchaseOrder) -> dict[str, Any]:
        return serialize_purchase_order(order)
