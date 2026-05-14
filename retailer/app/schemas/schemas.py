"""Pydantic schemas for the retailer's REST API.

The schemas mirror the SQLAlchemy models in `app/models/models.py` but
add the `schema_version` envelope on the response types so the
contract is forward-compatible. Same convention as the provider
(see `docs/PRD-week6.md` §7).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class CustomerOrderStatus(str, Enum):
    PENDING = "PENDING"
    BACKORDERED = "BACKORDERED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class PurchaseOrderStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class EventType(str, Enum):
    CUSTOMER_ORDER_PLACED = "CUSTOMER_ORDER_PLACED"
    CUSTOMER_ORDER_FULFILLED = "CUSTOMER_ORDER_FULFILLED"
    CUSTOMER_ORDER_BACKORDERED = "CUSTOMER_ORDER_BACKORDERED"
    CUSTOMER_ORDER_CANCELLED = "CUSTOMER_ORDER_CANCELLED"
    BACKORDER_FULFILLED = "BACKORDER_FULFILLED"
    PURCHASE_ORDER_PLACED = "PURCHASE_ORDER_PLACED"
    PURCHASE_ORDER_DELIVERED = "PURCHASE_ORDER_DELIVERED"
    PURCHASE_ORDER_REJECTED = "PURCHASE_ORDER_REJECTED"
    PURCHASE_ORDER_CANCELLED = "PURCHASE_ORDER_CANCELLED"
    PRICE_CHANGED = "PRICE_CHANGED"
    STOCK_ADDED = "STOCK_ADDED"
    STOCK_CONSUMED = "STOCK_CONSUMED"
    DAY_ADVANCED = "DAY_ADVANCED"


class CatalogEntry(BaseModel):
    product_name: str
    description: Optional[str] = None
    retail_price: Decimal

    model_config = ConfigDict(from_attributes=True)


class CatalogResponse(BaseModel):
    schema_version: int
    entries: list[CatalogEntry]


class StockLevel(BaseModel):
    product_name: str
    quantity: int
    last_updated: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StockResponse(BaseModel):
    schema_version: int
    items: list[StockLevel]


class CustomerOrderCreate(BaseModel):
    customer: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class CustomerOrder(BaseModel):
    id: int
    customer: str
    product_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    placed_day: int
    fulfilled_day: Optional[int] = None
    status: CustomerOrderStatus
    status_reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerOrderResponse(BaseModel):
    schema_version: int
    order: CustomerOrder


class PurchaseOrderCreate(BaseModel):
    product_name: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class PurchaseOrder(BaseModel):
    id: int
    manufacturer_name: str
    product_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    placed_day: int
    expected_delivery_day: Optional[int] = None
    delivered_day: Optional[int] = None
    status: PurchaseOrderStatus
    status_reason: Optional[str] = None
    external_order_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderResponse(BaseModel):
    schema_version: int
    order: PurchaseOrder


class DayCurrent(BaseModel):
    current_day: int


class DayAdvanceResult(BaseModel):
    previous_day: int
    current_day: int
    purchase_orders_delivered: int
    backorders_fulfilled: int


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
    product_name: str = Field(min_length=1)
    retail_price: Decimal = Field(gt=0)
