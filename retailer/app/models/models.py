"""SQLAlchemy models for the retailer app.

The shape follows `docs/PRD-week7.md` §4.1. Status fields are explicit
enums, never scattered booleans, per the conventions in `CLAUDE.md`.

Uses SQLAlchemy 2.0 declarative style with `Mapped[]` type annotations
and `mapped_column()` so that mypy --strict can check all column access.

Note: the retailer keys its catalog and stock by `product_name` (string)
rather than by a foreign-key id. The retailer does not share the
manufacturer's product table; it only knows the printer model names
that appear in its config and seed. Cross-app identity travels as
text over the wire (see PRD-week7 §3).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Any, Optional

from sqlalchemy import (
    DECIMAL,
    JSON,
    DateTime,
    Enum,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.utils.database import Base


class CatalogEntry(Base):
    """One printer model offered for sale by this retailer.

    `retail_price` is the price end customers pay. The pricing-floor
    rule (retail_price >= wholesale_price × 1.15) is enforced in the
    service layer, not in SQL — the floor depends on a live lookup
    against the manufacturer.
    """

    __tablename__ = "catalog"
    __table_args__ = {"extend_existing": True}

    product_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, default=None)
    retail_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)


class Stock(Base):
    """Current on-hand inventory of a finished-printer model."""

    __tablename__ = "stock"
    __table_args__ = {"extend_existing": True}

    product_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_updated: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class CustomerOrderStatus(PyEnum):
    """Lifecycle states for an order placed by an end customer.

    `PENDING → FULFILLED` is the happy path (immediate, when stock
    is available). `PENDING → BACKORDERED → FULFILLED` is the path
    when stock is empty at order time and arrives later. `CANCELLED`
    is a terminal short-circuit.
    """

    PENDING = "PENDING"
    BACKORDERED = "BACKORDERED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class CustomerOrder(Base):
    """An order placed by an end customer (synthetic in Week 7)."""

    __tablename__ = "customer_orders"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer: Mapped[str] = mapped_column(String(255), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    placed_day: Mapped[int] = mapped_column(Integer, nullable=False)
    fulfilled_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    status: Mapped[CustomerOrderStatus] = mapped_column(
        Enum(CustomerOrderStatus), nullable=False, default=CustomerOrderStatus.PENDING
    )
    status_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)


class PurchaseOrderStatus(PyEnum):
    """Lifecycle states for a PO this retailer placed with the manufacturer.

    Mirrors `manufacturer.PurchaseOrderStatus` and the Week 6 provider
    `OrderStatus` collapsed to the terminal-only states the retailer
    cares about. The manufacturer owns the on-the-wire intermediate
    states; the retailer only tracks pending vs delivered vs rejected.
    """

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PurchaseOrder(Base):
    """A purchase order this retailer placed with the manufacturer.

    `external_order_id` is the manufacturer's sales-order id, returned
    by `POST /api/sales/orders` and used for polling on day advance.
    """

    __tablename__ = "purchase_orders"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manufacturer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    placed_day: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_delivery_day: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
    delivered_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        Enum(PurchaseOrderStatus), nullable=False, default=PurchaseOrderStatus.PENDING
    )
    status_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    external_order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)


class EventType(PyEnum):
    """Event-log discriminator for the retailer's audit trail."""

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


class Event(Base):
    """Append-only audit log. One row per meaningful state change."""

    __tablename__ = "events"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    sim_day: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, default=None)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    details: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True, default=None)


class SimState(Base):
    """Single-table key/value store for the retailer's simulated time.

    Holds at minimum a row with `key='current_day'` whose value is the
    integer day, stored as text so the schema is future-proof for any
    other scalar bits of simulator state we need to keep across
    restarts.
    """

    __tablename__ = "sim_state"
    __table_args__ = {"extend_existing": True}

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
