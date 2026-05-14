"""FastAPI dependency providers."""

from __future__ import annotations

import os

from app.services.manufacturer_client import ManufacturerClient

_MANUFACTURER_URL = os.environ.get("RETAILER_MANUFACTURER_URL", "http://localhost:8002")


def get_manufacturer_client() -> ManufacturerClient:
    return ManufacturerClient(_MANUFACTURER_URL)
