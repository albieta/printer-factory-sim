"""SQLAlchemy models for the retailer app.

The shape follows `docs/PRD-week7.md` §4.1. Status fields are explicit
enums, never scattered booleans, per the conventions in `CLAUDE.md`.

Uses SQLAlchemy 2.0 declarative style with `Mapped[]` type annotations
and `mapped_column()` so that mypy --strict can check all column access.
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
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base


class CatalogItem(Base):
    """A printer model the retailer sells, with its current retail price.

    `model_name` is the canonical name used by the manufacturer (e.g.
    "P3D Classic"). It is the join key when the retailer posts a purchase
    order to the manufacturer's `POST /api/orders`.
    """

    __tablename__ = "catalog_items"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    retail_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    stock: Mapped[Optional["Stock"]] = relationship(
        "Stock",
        back_populates="catalog_item",
        uselist=False,
        cascade="all, delete-orphan",
    )
    customer_orders: Mapped[list["CustomerOrder"]] = relationship(
        "CustomerOrder",
        back_populates="catalog_item",
    )
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        "PurchaseOrder",
        back_populates="catalog_item",
    )


class Stock(Base):
    """Current on-hand inventory of a finished printer model, in whole units."""

    __tablename__ = "stock"
    __table_args__ = {"extend_existing": True}

    catalog_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("catalog_items.id"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_updated: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    catalog_item: Mapped["CatalogItem"] = relationship(
        "CatalogItem", back_populates="stock"
    )


class CustomerOrderStatus(PyEnum):
    """Lifecycle states for an order placed by an end customer.

    Happy path: `PENDING → FULFILLED`.
    Detour:     `PENDING → BACKORDERED → FULFILLED` (stock arrived later).
    Terminal:   `CANCELLED`.
    """

    PENDING = "PENDING"
    BACKORDERED = "BACKORDERED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class CustomerOrder(Base):
    """An order received from an end customer."""

    __tablename__ = "customer_orders"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("catalog_items.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    placed_day: Mapped[int] = mapped_column(Integer, nullable=False)
    fulfilled_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    status: Mapped[CustomerOrderStatus] = mapped_column(
        Enum(CustomerOrderStatus), nullable=False, default=CustomerOrderStatus.PENDING
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    catalog_item: Mapped["CatalogItem"] = relationship(
        "CatalogItem", back_populates="customer_orders"
    )


class PurchaseOrderStatus(PyEnum):
    """Lifecycle states for a purchase order the retailer places with the manufacturer.

    Mirrors the manufacturer's `SalesOrder` status so the retailer can map
    the polled response directly to its own row without translation.
    Happy path: `PENDING → CONFIRMED → IN_PROGRESS → SHIPPED → DELIVERED`.
    Terminal short-circuits from `PENDING`: `CANCELLED`, `REJECTED`.
    """

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PurchaseOrder(Base):
    """An order the retailer places with the manufacturer for finished printers."""

    __tablename__ = "purchase_orders"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("catalog_items.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    placed_day: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_delivery_day: Mapped[int] = mapped_column(Integer, nullable=False)
    delivered_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    # Manufacturer's SalesOrder id — used for polling GET /api/orders/{id}.
    external_order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        Enum(PurchaseOrderStatus), nullable=False, default=PurchaseOrderStatus.PENDING
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    catalog_item: Mapped["CatalogItem"] = relationship(
        "CatalogItem", back_populates="purchase_orders"
    )


class EventType(PyEnum):
    """Event-log discriminator for the retailer's audit trail."""

    CUSTOMER_ORDER_PLACED = "CUSTOMER_ORDER_PLACED"
    CUSTOMER_ORDER_FULFILLED = "CUSTOMER_ORDER_FULFILLED"
    CUSTOMER_ORDER_BACKORDERED = "CUSTOMER_ORDER_BACKORDERED"
    CUSTOMER_ORDER_CANCELLED = "CUSTOMER_ORDER_CANCELLED"
    PURCHASE_ORDER_PLACED = "PURCHASE_ORDER_PLACED"
    PURCHASE_ORDER_CONFIRMED = "PURCHASE_ORDER_CONFIRMED"
    PURCHASE_ORDER_IN_PROGRESS = "PURCHASE_ORDER_IN_PROGRESS"
    PURCHASE_ORDER_SHIPPED = "PURCHASE_ORDER_SHIPPED"
    PURCHASE_ORDER_DELIVERED = "PURCHASE_ORDER_DELIVERED"
    PURCHASE_ORDER_CANCELLED = "PURCHASE_ORDER_CANCELLED"
    PURCHASE_ORDER_REJECTED = "PURCHASE_ORDER_REJECTED"
    STOCK_RECEIVED = "STOCK_RECEIVED"
    PRICE_CHANGED = "PRICE_CHANGED"
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

    Holds at minimum a row with `key='current_day'` whose integer value
    is stored as text for future-proof extensibility.
    """

    __tablename__ = "sim_state"
    __table_args__ = {"extend_existing": True}

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
