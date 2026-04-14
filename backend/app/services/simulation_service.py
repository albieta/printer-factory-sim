from sqlalchemy.orm import Session
from app.models.models import Product, ProductType, ManufacturingOrder, Event, EventType
from app.services.config_service import ConfigService
from app.services.order_service import OrderService
from app.services.supplier_service import PurchaseOrderService
from app.services.production_service import ProductionService
from datetime import date
import random


class SimulationService:
    def __init__(self, db: Session):
        self.db = db
        self.config_service = ConfigService(db)
        self.order_service = OrderService(db)
        self.po_service = PurchaseOrderService(db)
        self.production_service = ProductionService(db)

    def advance_day(self) -> dict:
        """Execute one full simulation day"""
        # 1. Increment sim_date
        sim_date = self.config_service.advance_sim_date()
        
        # 2. Process PO deliveries
        po_results = self.po_service.process_deliveries(sim_date)
        pos_delivered = sum(1 for r in po_results if r["status"] == "delivered")
        
        # 3. Generate new orders based on demand distribution
        orders_created = self.generate_daily_demand(sim_date)
        
        # 4. Execute production
        production_results = self.production_service.execute_production(sim_date)
        orders_completed = sum(1 for r in production_results if r["status"] == "completed")
        
        # 5. Log day advanced event
        event = Event(
            event_type=EventType.DAY_ADVANCED,
            sim_date=sim_date,
            details={
                "orders_created": orders_created,
                "orders_completed": orders_completed,
                "pos_delivered": pos_delivered
            }
        )
        self.db.add(event)
        self.db.commit()
        
        return {
            "sim_date": sim_date,
            "events_generated": 1 + orders_created + pos_delivered + orders_completed,
            "orders_created": orders_created,
            "orders_completed": orders_completed,
            "purchase_orders_delivered": pos_delivered
        }

    def generate_daily_demand(self, sim_date: date) -> int:
        """Generate random manufacturing orders based on configuration"""
        config = self.config_service.get_config()
        
        # Get all printer models
        printer_models = self.db.query(Product).filter(Product.type == ProductType.PRINTER).all()
        if not printer_models:
            return 0
        
        # Generate number of orders based on normal distribution
        num_orders = max(0, int(random.gauss(config.demand_distribution_mean, config.demand_distribution_variance ** 0.5)))
        
        orders_created = 0
        for _ in range(num_orders):
            # Random printer model
            product = random.choice(printer_models)
            # Random quantity (1-10)
            quantity = random.randint(1, 10)
            
            self.order_service.create_order(product.id, quantity, sim_date)
            orders_created += 1
        
        return orders_created

    def get_simulation_status(self) -> dict:
        """Get current simulation state"""
        sim_date = self.config_service.get_sim_date()
        
        pending_orders = self.db.query(ManufacturingOrder).filter(
            ManufacturingOrder.status == "PENDING"
        ).count()
        
        completed_orders = self.db.query(ManufacturingOrder).filter(
            ManufacturingOrder.status == "COMPLETED"
        ).count()
        
        inventory_items = self.db.query(Product).filter(Product.type == ProductType.MATERIAL).count()
        
        total_events = self.db.query(Event).count()
        
        return {
            "current_date": sim_date,
            "pending_orders": pending_orders,
            "completed_orders": completed_orders,
            "inventory_items": inventory_items,
            "total_events": total_events
        }

    def reset_simulation(self) -> bool:
        """Reset simulation to initial state"""
        # Delete all events
        self.db.query(Event).delete()
        
        # Delete all manufacturing orders
        self.db.query(ManufacturingOrder).delete()
        
        # Delete all purchase orders
        from app.models.models import PurchaseOrder
        self.db.query(PurchaseOrder).delete()
        
        # Reset inventory to 0
        from app.models.models import Inventory
        inventory_items = self.db.query(Inventory).all()
        for inv in inventory_items:
            inv.quantity = 0
        
        # Reset sim_date to today
        config = self.config_service.get_config()
        config.sim_date = date.today()
        
        self.db.commit()
        return True
