"""Pydantic schemas for the retailer API.

Request bodies and response models for every endpoint defined in
`docs/PRD-week7.md` §4.3. The CLI reuses these models so the REST and
CLI surfaces stay structurally aligned.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


# ── Catalog ──────────────────────────────────────────────────────────────────


class CatalogItemOut(BaseModel):
    model_name: str
    retail_price: float


# ── Stock ────────────────────────────────────────────────────────────────────


class StockItemOut(BaseModel):
    model_name: str
    quantity: int


# ── Customer orders ──────────────────────────────────────────────────────────


class CustomerOrderCreate(BaseModel):
    model: str
    quantity: int = 1

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v


class CustomerOrderOut(BaseModel):
    id: int
    model_name: str
    quantity: int
    unit_price: float
    total_price: float
    placed_day: int
    fulfilled_day: Optional[int]
    status: str


# ── Purchase orders (retailer → manufacturer) ─────────────────────────────────


class PurchaseOrderCreate(BaseModel):
    model: str
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v


class PurchaseOrderOut(BaseModel):
    id: int
    model_name: str
    quantity: int
    unit_price: float
    total_price: float
    placed_day: int
    expected_delivery_day: int
    delivered_day: Optional[int]
    external_order_id: Optional[int]
    status: str


# ── Day ──────────────────────────────────────────────────────────────────────


class DayCurrentOut(BaseModel):
    current_day: int


class DayAdvanceOut(BaseModel):
    previous_day: int
    current_day: int
    deliveries_received: int
    backorders_fulfilled: int


# ── Price ────────────────────────────────────────────────────────────────────


class PriceSetRequest(BaseModel):
    price: float

    @field_validator("price")
    @classmethod
    def price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("price must be positive")
        return v
