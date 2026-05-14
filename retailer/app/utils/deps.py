"""FastAPI dependency providers."""

from __future__ import annotations

import os

from app.services.manufacturer_client import ManufacturerClient
from app.services.starter_profile import DEFAULT_MARKUP_PCT


def get_retailer_name() -> str:
    return os.environ.get("RETAILER_NAME", "PrinterWorld")


def get_manufacturer_name() -> str:
    return os.environ.get("RETAILER_MANUFACTURER_NAME", "Factory")


def get_markup_pct() -> int:
    return int(os.environ.get("RETAILER_MARKUP_PCT", str(DEFAULT_MARKUP_PCT)))


def get_manufacturer_client() -> ManufacturerClient:
    return ManufacturerClient(os.environ.get("RETAILER_MANUFACTURER_URL", "http://localhost:8002"))
