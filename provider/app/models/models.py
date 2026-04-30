"""SQLAlchemy models for the provider app.

The shape follows `docs/PRD-week6.md` §5.1. Status fields are explicit
enums, never scattered booleans, per the conventions in `CLAUDE.md`.

The provider uses integer primary keys (matching the example schema in
the Week 6 brief). The manufacturer uses UUID strings; the two apps are
independent processes with no shared identifiers, so the difference is
fine.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    DECIMAL,
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

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

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    lead_time_days = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    pricing_tiers = relationship(
        "PricingTier",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="PricingTier.min_quantity",
    )
    stock = relationship(
        "Stock",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )
    orders = relationship("Order", back_populates="product")


class PricingTier(Base):
    """One quantity break for a product.

    A product with three pricing tiers (1, 20, 200) charges the
    corresponding `unit_price` for every unit in an order whose quantity
    is ≥ `min_quantity` and below the next tier's threshold.
    """

    __tablename__ = "pricing_tiers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    min_quantity = Column(Integer, nullable=False)
    unit_price = Column(DECIMAL(10, 2), nullable=False)

    product = relationship("Product", back_populates="pricing_tiers")


class Stock(Base):
    """Current on-hand inventory of a product, in whole units."""

    __tablename__ = "stock"
    __table_args__ = {"extend_existing": True}

    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    quantity = Column(Integer, nullable=False, default=0)
    last_updated = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    product = relationship("Product", back_populates="stock")


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

    id = Column(Integer, primary_key=True, autoincrement=True)
    buyer = Column(String(255), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(DECIMAL(10, 2), nullable=False)
    total_price = Column(DECIMAL(12, 2), nullable=False)
    placed_day = Column(Integer, nullable=False)
    expected_delivery_day = Column(Integer, nullable=False)
    shipped_day = Column(Integer, nullable=True)
    delivered_day = Column(Integer, nullable=True)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    status_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="orders")


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

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(Enum(EventType), nullable=False)
    sim_day = Column(Integer, nullable=False)
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(JSON, nullable=True)


class SimState(Base):
    """Single-table key/value store for the provider's simulated time.

    Holds at minimum a row with `key='current_day'` whose value is the
    integer day, stored as text so the schema is future-proof for any
    other scalar bits of simulator state we need to keep across
    restarts.
    """

    __tablename__ = "sim_state"
    __table_args__ = {"extend_existing": True}

    key = Column(String(64), primary_key=True)
    value = Column(String(255), nullable=False)
