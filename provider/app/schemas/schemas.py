from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class EventType(str, Enum):
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    ORDER_IN_PROGRESS = "ORDER_IN_PROGRESS"
    ORDER_SHIPPED = "ORDER_SHIPPED"
    ORDER_DELIVERED = "ORDER_DELIVERED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    PRICE_CHANGED = "PRICE_CHANGED"
    STOCK_RESTOCKED = "STOCK_RESTOCKED"
    STOCK_CONSUMED = "STOCK_CONSUMED"
    DAY_ADVANCED = "DAY_ADVANCED"


class PricingTier(BaseModel):
    min_quantity: int
    unit_price: Decimal

    model_config = ConfigDict(from_attributes=True)


class Product(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    lead_time_days: int
    pricing_tiers: list[PricingTier] = []
    stock_quantity: int = 0


class CatalogResponse(BaseModel):
    schema_version: int
    products: list[Product]


class StockLevel(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    last_updated: Optional[datetime] = None


class OrderCreate(BaseModel):
    buyer: str = Field(min_length=1)
    product_id: int
    quantity: int = Field(gt=0)


class Order(BaseModel):
    id: int
    buyer: str
    product_id: int
    product_name: Optional[str] = None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    placed_day: int
    expected_delivery_day: int
    shipped_day: Optional[int] = None
    delivered_day: Optional[int] = None
    status: OrderStatus
    status_reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    schema_version: int
    order: Order


class DayCurrent(BaseModel):
    current_day: int


class DayAdvanceResult(BaseModel):
    previous_day: int
    current_day: int
    orders_shipped: int
    orders_delivered: int


class Event(BaseModel):
    id: int
    event_type: EventType
    sim_day: int
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    timestamp: datetime
    details: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class PriceSetRequest(BaseModel):
    product_id: int
    min_quantity: int = Field(gt=0)
    unit_price: Decimal = Field(gt=0)


class RestockRequest(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
