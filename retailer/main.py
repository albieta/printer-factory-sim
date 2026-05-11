"""FastAPI entrypoint for the retailer app.

Config is read from the `RETAILER_CONFIG` environment variable (path to
a retailer JSON file). When started via `retailer-cli serve`, the CLI
sets this variable before handing off to uvicorn so callers only need
the `--config` flag on the CLI.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.routes import catalog, day, health, orders, purchases, stock
from app.utils.config import load_config
from app.utils.database import bootstrap_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config_path = Path(os.environ.get("RETAILER_CONFIG", "retailer.json"))
    cfg = load_config(config_path)
    bootstrap_database(cfg.db_path)
    app.state.config = cfg
    yield


app = FastAPI(
    title="Retailer API",
    description="Week 7 retailer — buys finished printers from the manufacturer and sells to end customers.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(catalog.router, prefix="/api/catalog", tags=["catalog"])
app.include_router(stock.router, prefix="/api/stock", tags=["stock"])
app.include_router(orders.router, prefix="/api/orders", tags=["customer-orders"])
app.include_router(purchases.router, prefix="/api/purchases", tags=["purchase-orders"])
app.include_router(day.router, prefix="/api/day", tags=["day"])
app.include_router(health.router, prefix="/health", tags=["health"])
