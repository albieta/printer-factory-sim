from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

RETAILER_ROOT = Path(__file__).resolve().parent
os.chdir(RETAILER_ROOT)
sys.path.insert(0, str(RETAILER_ROOT))

from app.api.routes import router  # noqa: E402
from app.utils.database import bootstrap_database  # noqa: E402

bootstrap_database()

app = FastAPI(
    title="3D Printer Retailer",
    description="Retailer app for the Week 7 distributed supply-chain simulation.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
