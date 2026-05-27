from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Any, Optional

from sqlalchemy import (
    DECIMAL,
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base


class ProductType(PyEnum):
    PRINTER = "PRINTER"
    MATERIAL = "MATERIAL"


class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[ProductType] = mapped_column(Enum(ProductType), nullable=False)
    assembly_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    bom_entries: Mapped[list["BillOfMaterials"]] = relationship(
        "BillOfMaterials",
        back_populates="finished_product",
        foreign_keys="BillOfMaterials.finished_product_id",
    )
    manufacturing_orders: Mapped[list["ManufacturingOrder"]] = relationship(
        "ManufacturingOrder", back_populates="product"
    )


class BillOfMaterials(Base):
    __tablename__ = "bill_of_materials"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    finished_product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id"), nullable=False
    )
    material_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)

    finished_product: Mapped["Product"] = relationship(
        "Product",
        back_populates="bom_entries",
        foreign_keys="[BillOfMaterials.finished_product_id]",
    )
    material: Mapped["Product"] = relationship(
        "Product", foreign_keys="[BillOfMaterials.material_id]"
    )


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id"), nullable=False
    )
    unit_cost: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_breaks: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True, default=None)
    external_provider_url: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    external_product_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )

    product: Mapped["Product"] = relationship("Product")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        "PurchaseOrder", back_populates="supplier"
    )


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = {"extend_existing": True}

    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id"), primary_key=True
    )
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, default=0)
    last_updated: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    product: Mapped["Product"] = relationship("Product")


class OrderStatus(PyEnum):
    PENDING = "PENDING"
    RELEASED = "RELEASED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


class ManufacturingOrder(Base):
    __tablename__ = "manufacturing_orders"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    reference_code: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, unique=True, default=None
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING
    )
    status_reason: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    created_date: Mapped[date] = mapped_column(Date, nullable=False)
    released_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, default=None)
    completed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, default=None)

    product: Mapped["Product"] = relationship("Product", back_populates="manufacturing_orders")


class PurchaseOrderStatus(PyEnum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    reference_code: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, unique=True, default=None
    )
    supplier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("suppliers.id"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_delivery: Mapped[date] = mapped_column(Date, nullable=False)
    actual_delivery: Mapped[Optional[date]] = mapped_column(Date, nullable=True, default=None)
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        Enum(PurchaseOrderStatus), nullable=False, default=PurchaseOrderStatus.PENDING
    )
    status_reason: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    unit_cost: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    external_order_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )

    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="purchase_orders")
    product: Mapped["Product"] = relationship("Product")


class EventType(PyEnum):
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_RELEASED = "ORDER_RELEASED"
    ORDER_BLOCKED_MATERIALS = "ORDER_BLOCKED_MATERIALS"
    ORDER_UNBLOCKED_MATERIALS = "ORDER_UNBLOCKED_MATERIALS"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_STARTED = "ORDER_STARTED"
    ORDER_COMPLETED = "ORDER_COMPLETED"
    PO_CREATED = "PO_CREATED"
    PO_DELIVERED = "PO_DELIVERED"
    PO_REJECTED = "PO_REJECTED"
    PO_REJECTED_CAPACITY = "PO_REJECTED_CAPACITY"
    MATERIAL_CONSUMED = "MATERIAL_CONSUMED"
    INVENTORY_ADDED = "INVENTORY_ADDED"
    DAY_ADVANCED = "DAY_ADVANCED"
    PRODUCTION_BLOCKED_CAPACITY = "PRODUCTION_BLOCKED_CAPACITY"
    SALES_ORDER_PLACED = "SALES_ORDER_PLACED"
    SALES_ORDER_RELEASED = "SALES_ORDER_RELEASED"
    SALES_ORDER_REJECTED = "SALES_ORDER_REJECTED"
    SALES_ORDER_SHIPPED = "SALES_ORDER_SHIPPED"
    SALES_ORDER_DELIVERED = "SALES_ORDER_DELIVERED"
    WHOLESALE_PRICE_CHANGED = "WHOLESALE_PRICE_CHANGED"


class Event(Base):
    __tablename__ = "events"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    sim_date: Mapped[date] = mapped_column(Date, nullable=False)
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    details: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True, default=None)


class SimulationConfig(Base):
    __tablename__ = "simulation_config"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    warehouse_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=2200)
    daily_assembly_hours: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    assembly_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    workers_per_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    shift_hours: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    demand_distribution_mean: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    demand_distribution_variance: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    internal_demand_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sim_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    sim_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_per_assembly_line: Mapped[float] = mapped_column(Float, nullable=False, default=50000.0)
    cost_per_assembly_line_per_day: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    cost_per_worker_per_hour: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    max_workers_per_line: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    total_costs: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_revenue: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    provider_urls: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True, default=None)
    retailer_demand_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retailer_demand_mean: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    retailer_demand_variance: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    retailer_demand_modifier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    retailer_demand_base_price: Mapped[float] = mapped_column(Float, nullable=False, default=400.0)


class SalesOrderStatus(PyEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class SalesOrder(Base):
    """Inbound order placed by a retailer for finished printers."""

    __tablename__ = "sales_orders"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    reference_code: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, unique=True, default=None
    )
    retailer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SalesOrderStatus] = mapped_column(
        Enum(SalesOrderStatus), nullable=False, default=SalesOrderStatus.PENDING
    )
    status_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    placed_day: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_ship_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    in_progress_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    shipped_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    delivered_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    linked_mfg_order_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("manufacturing_orders.id"), nullable=True, default=None
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["Product"] = relationship("Product")
    linked_mfg_order: Mapped[Optional["ManufacturingOrder"]] = relationship(
        "ManufacturingOrder", foreign_keys=[linked_mfg_order_id]
    )


class WholesalePrice(Base):
    """Manufacturer's wholesale price per finished-printer model."""

    __tablename__ = "wholesale_prices"
    __table_args__ = {"extend_existing": True}

    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id"), primary_key=True
    )
    price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["Product"] = relationship("Product")


class FinancialTransactionType(PyEnum):
    ASSEMBLY_LINE_OPENED = "ASSEMBLY_LINE_OPENED"
    WORKER_HIRED = "WORKER_HIRED"
    MATERIALS_PURCHASED = "MATERIALS_PURCHASED"
    PRODUCT_SOLD = "PRODUCT_SOLD"
    WORKER_FIRED = "WORKER_FIRED"
    ASSEMBLY_LINE_CLOSED = "ASSEMBLY_LINE_CLOSED"
    ASSEMBLY_LINE_DAILY_COST = "ASSEMBLY_LINE_DAILY_COST"
    WORKER_DAILY_COST = "WORKER_DAILY_COST"


class FinancialTransaction(Base):
    """Track all financial activity: costs and revenues."""

    __tablename__ = "financial_transactions"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_type: Mapped[FinancialTransactionType] = mapped_column(
        Enum(FinancialTransactionType), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    sim_day: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
