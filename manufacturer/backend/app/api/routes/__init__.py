from fastapi import APIRouter

from app.api.routes.capacity import router as capacity_router
from app.api.routes.config import router as config_router
from app.api.routes.events import router as events_router
from app.api.routes.import_export import router as import_export_router
from app.api.routes.inventory import router as inventory_router
from app.api.routes.materials import router as materials_router
from app.api.routes.orders import router as orders_router
from app.api.routes.prices import router as prices_router
from app.api.routes.production import router as production_router
from app.api.routes.purchase_orders import router as purchase_orders_router
from app.api.routes.sales import router as sales_router
from app.api.routes.scenarios import router as scenarios_router
from app.api.routes.simulation import router as simulation_router
from app.api.routes.suppliers import router as suppliers_router

router = APIRouter()

# Week 5/6 routes — unchanged
router.include_router(config_router, prefix="/config", tags=["Configuration"])
router.include_router(materials_router, prefix="/materials", tags=["Materials & BOM"])
router.include_router(suppliers_router, prefix="/suppliers", tags=["Suppliers"])
router.include_router(inventory_router, prefix="/inventory", tags=["Inventory"])
router.include_router(orders_router, prefix="/orders", tags=["Manufacturing Orders"])
router.include_router(purchase_orders_router, prefix="/orders/purchase", tags=["Purchase Orders"])
router.include_router(simulation_router, prefix="/simulation", tags=["Simulation"])
router.include_router(events_router, prefix="/events", tags=["Events"])
router.include_router(import_export_router, tags=["Import/Export"])

# Week 7 additions
router.include_router(sales_router, prefix="/sales/orders", tags=["Sales Orders"])
router.include_router(production_router, prefix="/production", tags=["Production"])
router.include_router(capacity_router, prefix="/capacity", tags=["Capacity"])
router.include_router(prices_router, prefix="/prices", tags=["Wholesale Prices"])

# Week 8: scenario launcher + live log/metrics viewer for the UI
router.include_router(scenarios_router, prefix="/scenarios", tags=["Scenarios"])
