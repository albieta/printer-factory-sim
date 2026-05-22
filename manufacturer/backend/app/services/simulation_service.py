from __future__ import annotations
from typing import Any

import random
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.models import Event, EventType, ManufacturingOrder, OrderStatus, Product, ProductType, PurchaseOrder, PurchaseOrderStatus, BillOfMaterials, Supplier, Inventory
from app.services.config_service import ConfigService
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService
from app.services.production_service import ProductionService
from app.services.starter_profile import STARTER_INVENTORY, STARTER_PRINTERS, STARTER_MATERIALS, STARTER_BOM, WORKFLOW_STAGE_DEFS, build_starter_config
from app.services.supplier_service import PurchaseOrderService
from app.utils.database import apply_external_provider_config


class SimulationService:
    def __init__(self, db: Session):
        self.db = db
        self.config_service = ConfigService(db)
        self.order_service = OrderService(db)
        self.po_service = PurchaseOrderService(db)
        self.production_service = ProductionService(db)
        self.inventory_service = InventoryService(db)

    def advance_day(self) -> dict[str, Any]:
        sim_date = self.config_service.advance_sim_date()

        po_results = self.po_service.process_deliveries(sim_date)
        pos_delivered = sum(1 for result in po_results if result["status"] == "delivered")

        orders_created = self.generate_daily_demand(sim_date)
        self.order_service.recheck_blocked_orders(sim_date)

        production_results = self.production_service.execute_production(sim_date)
        orders_completed = sum(1 for result in production_results if result["status"] == "completed")

        from app.services.sales_order_service import SalesOrderService

        sim_day = self.config_service.get_sim_day()
        so_counts = SalesOrderService(self.db).progress_sales_orders(sim_day)

        event = Event(
            event_type=EventType.DAY_ADVANCED,
            sim_date=sim_date,
            details={
                "orders_created": orders_created,
                "orders_completed": orders_completed,
                "pos_delivered": pos_delivered,
                "so_in_progress": so_counts["in_progress"],
                "so_shipped": so_counts["shipped"],
                "so_delivered": so_counts["delivered"],
            },
        )
        self.db.add(event)
        self.db.commit()

        return {
            "sim_date": sim_date,
            "events_generated": 1 + orders_created + pos_delivered + orders_completed,
            "orders_created": orders_created,
            "orders_completed": orders_completed,
            "purchase_orders_delivered": pos_delivered,
            "sales_orders_in_progress": so_counts["in_progress"],
            "sales_orders_shipped": so_counts["shipped"],
            "sales_orders_delivered": so_counts["delivered"],
        }

    def generate_daily_demand(self, sim_date: date) -> int:
        config = self.config_service.get_config()
        printer_models = self.db.query(Product).filter(Product.type == ProductType.PRINTER).all()
        if not printer_models:
            return 0

        num_orders = max(0, int(random.gauss(config.demand_distribution_mean, config.demand_distribution_variance ** 0.5)))
        orders_created = 0

        for _ in range(num_orders):
            product = random.choice(printer_models)
            quantity = random.randint(1, 10)
            self.order_service.create_order(product.id, quantity, sim_date)
            orders_created += 1

        return orders_created

    def build_workflow_stages(self) -> list[dict[str, Any]]:
        capacity = self.inventory_service.get_capacity_info()
        pending_orders = self.db.query(ManufacturingOrder).filter(ManufacturingOrder.status == OrderStatus.PENDING).count()
        blocked_orders = self.db.query(ManufacturingOrder).filter(ManufacturingOrder.status == OrderStatus.BLOCKED).count()
        released_orders = self.db.query(ManufacturingOrder).filter(ManufacturingOrder.status == OrderStatus.RELEASED).count()
        completed_orders = self.db.query(ManufacturingOrder).filter(ManufacturingOrder.status == OrderStatus.COMPLETED).count()
        pending_purchase_orders = self.db.query(PurchaseOrder).filter(PurchaseOrder.status == PurchaseOrderStatus.PENDING).count()

        values = {
            "demand": f"{pending_orders + blocked_orders} orders waiting",
            "release": f"{pending_orders} awaiting release",
            "assembly": f"{released_orders} queued in assembly",
            "procurement": f"{pending_purchase_orders} POs in transit",
            "storage": f"{capacity['current_usage']:.0f} / {capacity['warehouse_capacity']} units stored",
            "outcomes": f"{completed_orders} completed orders",
        }

        return [
            {
                **stage,
                "value": values[stage["key"]],
            }
            for stage in WORKFLOW_STAGE_DEFS
        ]

    def get_simulation_status(self) -> dict[str, Any]:
        config = self.config_service.get_config()
        capacity = self.inventory_service.get_capacity_info()

        pending_orders = self.db.query(ManufacturingOrder).filter(ManufacturingOrder.status == OrderStatus.PENDING).count()
        released_orders = self.db.query(ManufacturingOrder).filter(ManufacturingOrder.status == OrderStatus.RELEASED).count()
        blocked_orders = self.db.query(ManufacturingOrder).filter(ManufacturingOrder.status == OrderStatus.BLOCKED).count()
        completed_orders = self.db.query(ManufacturingOrder).filter(ManufacturingOrder.status == OrderStatus.COMPLETED).count()
        rejected_orders = self.db.query(ManufacturingOrder).filter(ManufacturingOrder.status == OrderStatus.REJECTED).count()
        pending_purchase_orders = self.db.query(PurchaseOrder).filter(PurchaseOrder.status == PurchaseOrderStatus.PENDING).count()
        delivered_purchase_orders = self.db.query(PurchaseOrder).filter(PurchaseOrder.status == PurchaseOrderStatus.DELIVERED).count()
        rejected_purchase_orders = self.db.query(PurchaseOrder).filter(PurchaseOrder.status == PurchaseOrderStatus.REJECTED).count()
        inventory_items = self.db.query(Product).filter(Product.type == ProductType.MATERIAL).count()
        total_events = self.db.query(Event).count()

        return {
            "current_date": config.sim_date,
            "pending_orders": pending_orders,
            "released_orders": released_orders,
            "blocked_orders": blocked_orders,
            "completed_orders": completed_orders,
            "rejected_orders": rejected_orders,
            "pending_purchase_orders": pending_purchase_orders,
            "delivered_purchase_orders": delivered_purchase_orders,
            "rejected_purchase_orders": rejected_purchase_orders,
            "inventory_items": inventory_items,
            "total_events": total_events,
            "warehouse_capacity": capacity["warehouse_capacity"],
            "current_usage": capacity["current_usage"],
            "available_capacity": capacity["available_capacity"],
            "usage_percentage": capacity["usage_percentage"],
            "assembly_lines": config.assembly_lines,
            "workers_per_line": config.workers_per_line,
            "shift_hours": config.shift_hours,
            "effective_daily_assembly_hours": self.config_service.get_effective_daily_assembly_hours(config),
            "workflow_stages": self.build_workflow_stages(),
        }

    def reset_simulation(self) -> bool:
        starter_config = build_starter_config(sim_date=date.today())

        self.db.query(Event).delete()
        self.db.query(ManufacturingOrder).delete()
        self.db.query(PurchaseOrder).delete()

        material_lookup = {
            material.name: material.id
            for material in self.db.query(Product).filter(Product.type == ProductType.MATERIAL).all()
        }

        inventory_items = self.db.query(Inventory).all()
        for inventory in inventory_items:
            inventory.quantity = Decimal(0)

        for material_name, quantity in STARTER_INVENTORY.items():
            product_id = material_lookup.get(material_name)
            if not product_id:
                material = Product(name=material_name, type=ProductType.MATERIAL)
                self.db.add(material)
                self.db.flush()
                product_id = material.id
            inventory = self.inventory_service.get_inventory_by_product(product_id)
            inventory.quantity = Decimal(quantity)

        config = self.config_service.get_config()
        for key, value in starter_config.items():
            setattr(config, key, value)

        self.db.commit()
        return True

    def reset_to_empty(self) -> bool:
        """Delete all data except simulation config and start fresh."""
        self.db.query(Event).delete()
        self.db.query(ManufacturingOrder).delete()
        self.db.query(PurchaseOrder).delete()
        self.db.query(BillOfMaterials).delete()
        self.db.query(Inventory).delete()
        self.db.query(Product).delete()
        self.db.query(Supplier).delete()

        config = self.config_service.get_config()
        starter_config = build_starter_config(sim_date=date.today())
        for key, value in starter_config.items():
            setattr(config, key, value)

        # Reset custom provider URLs to use defaults from config.json
        config.provider_urls = None

        self.db.commit()
        return True

    def reset_to_default_config(self) -> bool:
        """Reset to starter profile with all default data."""
        self.reset_to_empty()

        product_lookup: dict[str, Product] = {}

        for printer_data in STARTER_PRINTERS:
            printer = Product(
                name=printer_data["name"],
                type=ProductType.PRINTER,
                assembly_hours=printer_data["assembly_hours"],
            )
            self.db.add(printer)
            product_lookup[printer.name] = printer
        self.db.commit()

        for material_name in STARTER_MATERIALS:
            material = Product(name=material_name, type=ProductType.MATERIAL)
            self.db.add(material)
            product_lookup[material.name] = material
        self.db.commit()

        for printer_name, entries in STARTER_BOM.items():
            for entry in entries:
                self.db.add(
                    BillOfMaterials(
                        finished_product_id=product_lookup[printer_name].id,
                        material_id=product_lookup[entry["material"]].id,
                        quantity=entry["quantity"],
                    )
                )
        self.db.commit()

        for material_name, quantity in STARTER_INVENTORY.items():
            self.db.add(Inventory(product_id=product_lookup[material_name].id, quantity=quantity))
        self.db.commit()

        apply_external_provider_config(self.db)
        self.db.commit()
        return True
