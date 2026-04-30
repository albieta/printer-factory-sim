from fastapi import APIRouter

from app.api.routes.catalog import router as catalog_router
from app.api.routes.day import router as day_router
from app.api.routes.events import router as events_router
from app.api.routes.orders import router as orders_router
from app.api.routes.stock import router as stock_router

router = APIRouter()

router.include_router(catalog_router, prefix="/catalog", tags=["Catalog"])
router.include_router(stock_router, prefix="/stock", tags=["Stock"])
router.include_router(orders_router, prefix="/orders", tags=["Orders"])
router.include_router(day_router, prefix="/day", tags=["Day"])
router.include_router(events_router, prefix="/events", tags=["Events"])
