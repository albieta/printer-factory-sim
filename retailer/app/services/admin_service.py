"""JSON export / import for the retailer app.

Export serialises the full database state to a dict suitable for
`json.dumps`. Import truncates all tables and reloads from the dict —
designed for dev/test state snapshots, not production migration.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import (
    CatalogItem,
    CustomerOrder,
    CustomerOrderStatus,
    Event,
    EventType,
    PurchaseOrder,
    PurchaseOrderStatus,
    SimState,
    Stock,
)


class AdminService:
    SCHEMA_VERSION = 1

    def __init__(self, db: Session) -> None:
        self._db = db

    def export_state(self) -> dict[str, Any]:
        """Serialise full DB state to a JSON-safe dict."""
        sim = self._db.query(SimState).all()
        items = self._db.query(CatalogItem).order_by(CatalogItem.id).all()
        stock = self._db.query(Stock).all()
        cos = self._db.query(CustomerOrder).order_by(CustomerOrder.id).all()
        pos = self._db.query(PurchaseOrder).order_by(PurchaseOrder.id).all()
        events = self._db.query(Event).order_by(Event.id).all()

        return {
            "schema_version": self.SCHEMA_VERSION,
            "sim_state": {row.key: row.value for row in sim},
            "catalog": [
                {
                    "id": i.id,
                    "model_name": i.model_name,
                    "retail_price": float(i.retail_price),
                }
                for i in items
            ],
            "stock": [
                {"catalog_item_id": s.catalog_item_id, "quantity": s.quantity}
                for s in stock
            ],
            "customer_orders": [
                {
                    "id": o.id,
                    "catalog_item_id": o.catalog_item_id,
                    "quantity": o.quantity,
                    "unit_price": float(o.unit_price),
                    "total_price": float(o.total_price),
                    "placed_day": o.placed_day,
                    "fulfilled_day": o.fulfilled_day,
                    "status": o.status.value,
                }
                for o in cos
            ],
            "purchase_orders": [
                {
                    "id": po.id,
                    "catalog_item_id": po.catalog_item_id,
                    "quantity": po.quantity,
                    "unit_price": float(po.unit_price),
                    "total_price": float(po.total_price),
                    "placed_day": po.placed_day,
                    "expected_delivery_day": po.expected_delivery_day,
                    "delivered_day": po.delivered_day,
                    "external_order_id": po.external_order_id,
                    "status": po.status.value,
                }
                for po in pos
            ],
            "events": [
                {
                    "id": e.id,
                    "event_type": e.event_type.value,
                    "sim_day": e.sim_day,
                    "entity_type": e.entity_type,
                    "entity_id": e.entity_id,
                    "details": e.details,
                }
                for e in events
            ],
        }

    def import_state(self, data: dict[str, Any]) -> None:
        """Truncate all tables and reload from `data`.

        Validates schema version before touching the database.
        """
        if data.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError(
                f"schema_version mismatch: got {data.get('schema_version')!r}, "
                f"expected {self.SCHEMA_VERSION}"
            )

        # Clear in FK-safe order.
        self._db.query(Event).delete()
        self._db.query(CustomerOrder).delete()
        self._db.query(PurchaseOrder).delete()
        self._db.query(Stock).delete()
        self._db.query(CatalogItem).delete()
        self._db.query(SimState).delete()
        self._db.flush()

        for entry in data.get("catalog", []):
            self._db.add(
                CatalogItem(
                    id=entry["id"],
                    model_name=entry["model_name"],
                    retail_price=Decimal(str(entry["retail_price"])),
                )
            )
        self._db.flush()

        for entry in data.get("stock", []):
            self._db.add(
                Stock(
                    catalog_item_id=entry["catalog_item_id"],
                    quantity=entry["quantity"],
                )
            )

        for entry in data.get("customer_orders", []):
            self._db.add(
                CustomerOrder(
                    id=entry["id"],
                    catalog_item_id=entry["catalog_item_id"],
                    quantity=entry["quantity"],
                    unit_price=Decimal(str(entry["unit_price"])),
                    total_price=Decimal(str(entry["total_price"])),
                    placed_day=entry["placed_day"],
                    fulfilled_day=entry.get("fulfilled_day"),
                    status=CustomerOrderStatus(entry["status"]),
                )
            )

        for entry in data.get("purchase_orders", []):
            self._db.add(
                PurchaseOrder(
                    id=entry["id"],
                    catalog_item_id=entry["catalog_item_id"],
                    quantity=entry["quantity"],
                    unit_price=Decimal(str(entry["unit_price"])),
                    total_price=Decimal(str(entry["total_price"])),
                    placed_day=entry["placed_day"],
                    expected_delivery_day=entry["expected_delivery_day"],
                    delivered_day=entry.get("delivered_day"),
                    external_order_id=entry.get("external_order_id"),
                    status=PurchaseOrderStatus(entry["status"]),
                )
            )

        for key, value in data.get("sim_state", {}).items():
            self._db.add(SimState(key=key, value=str(value)))

        self._db.commit()
