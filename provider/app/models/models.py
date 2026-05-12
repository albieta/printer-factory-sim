"""SQLAlchemy models for the provider app.

The shape follows `docs/PRD-week6.md` §5.1. Status fields are explicit
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


class Product(Base):
    """A part the provider sells (e.g., "Control Board", "Stepper Motor").

    `lead_time_days` is the contractual minimum number of simulated days
    between order placement and delivery. The Week 6 "ironclad rule"
    requires this to be at least 1 — enforced at the service layer, not
    in SQL, so seed data can keep its raw integers.
    """

    __tablename__ = "products"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, default=None)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    pricing_tiers: Mapped[list["PricingTier"]] = relationship(
        "PricingTier",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="PricingTier.min_quantity",
    )
    stock: Mapped[Optional["Stock"]] = relationship(
        "Stock",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="product")


class PricingTier(Base):
    """One quantity break for a product.

    A product with three pricing tiers (1, 20, 200) charges the
    corresponding `unit_price` for every unit in an order whose quantity
    is ≥ `min_quantity` and below the next tier's threshold.
    """

    __tablename__ = "pricing_tiers"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)

    product: Mapped["Product"] = relationship("Product", back_populates="pricing_tiers")


class Stock(Base):
    """Current on-hand inventory of a product, in whole units."""

    __tablename__ = "stock"
    __table_args__ = {"extend_existing": True}

    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_updated: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    product: Mapped["Product"] = relationship("Product", back_populates="stock")


class OrderStatus(PyEnum):
    """Lifecycle states for an order received by the provider.

    `PENDING → CONFIRMED → IN_PROGRESS → SHIPPED → DELIVERED` is the
    happy path. `REJECTED` and `CANCELLED` are terminal short-circuits
    available from `PENDING`.
    """

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class Order(Base):
    """A purchase order received from a buyer (the manufacturer)."""

    __tablename__ = "orders"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    placed_day: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_delivery_day: Mapped[int] = mapped_column(Integer, nullable=False)
    shipped_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    delivered_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING
    )
    status_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["Product"] = relationship("Product", back_populates="orders")


class EventType(PyEnum):
    """Event-log discriminator for the provider's audit trail."""

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
    """Single-table key/value store for the provider's simulated time.

    Holds at minimum a row with `key='current_day'` whose value is the
    integer day, stored as text so the schema is future-proof for any
    other scalar bits of simulator state we need to keep across
    restarts.
    """

    __tablename__ = "sim_state"
    __table_args__ = {"extend_existing": True}

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
