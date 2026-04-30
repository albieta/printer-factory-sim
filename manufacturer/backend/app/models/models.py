import uuid
from datetime import datetime, date
from enum import Enum as PyEnum

from sqlalchemy import Column, String, Integer, Float, DateTime, Date, Enum, ForeignKey, JSON, DECIMAL
from sqlalchemy.orm import relationship

from app.utils.database import Base


class ProductType(PyEnum):
    PRINTER = "PRINTER"
    MATERIAL = "MATERIAL"


class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"extend_existing": True}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    type = Column(Enum(ProductType), nullable=False)
    assembly_hours = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bom_entries = relationship(
        "BillOfMaterials",
        back_populates="finished_product",
        foreign_keys="BillOfMaterials.finished_product_id",
    )
    manufacturing_orders = relationship("ManufacturingOrder", back_populates="product")


class BillOfMaterials(Base):
    __tablename__ = "bill_of_materials"
    __table_args__ = {"extend_existing": True}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    finished_product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    material_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    quantity = Column(DECIMAL(10, 2), nullable=False)

    finished_product = relationship("Product", back_populates="bom_entries", foreign_keys=[finished_product_id])
    material = relationship("Product", foreign_keys=[material_id])


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = {"extend_existing": True}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    unit_cost = Column(DECIMAL(10, 2), nullable=False)
    lead_time_days = Column(Integer, nullable=False)
    quantity_breaks = Column(JSON, nullable=True)
    external_provider_url = Column(String(255), nullable=True)
    external_product_id = Column(Integer, nullable=True)

    product = relationship("Product")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = {"extend_existing": True}

    product_id = Column(String(36), ForeignKey("products.id"), primary_key=True)
    quantity = Column(DECIMAL(10, 2), nullable=False, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = relationship("Product")


class OrderStatus(PyEnum):
    PENDING = "PENDING"
    RELEASED = "RELEASED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


class ManufacturingOrder(Base):
    __tablename__ = "manufacturing_orders"
    __table_args__ = {"extend_existing": True}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reference_code = Column(String(32), nullable=True, unique=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    status_reason = Column(String(255), nullable=True)
    created_date = Column(Date, nullable=False)
    released_date = Column(Date, nullable=True)
    completed_date = Column(Date, nullable=True)

    product = relationship("Product", back_populates="manufacturing_orders")


class PurchaseOrderStatus(PyEnum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = {"extend_existing": True}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reference_code = Column(String(32), nullable=True, unique=True)
    supplier_id = Column(String(36), ForeignKey("suppliers.id"), nullable=False)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    issue_date = Column(Date, nullable=False)
    expected_delivery = Column(Date, nullable=False)
    actual_delivery = Column(Date, nullable=True)
    status = Column(Enum(PurchaseOrderStatus), nullable=False, default=PurchaseOrderStatus.PENDING)
    status_reason = Column(String(255), nullable=True)
    unit_cost = Column(DECIMAL(10, 2), nullable=False)
    external_order_id = Column(Integer, nullable=True)

    supplier = relationship("Supplier", back_populates="purchase_orders")
    product = relationship("Product")


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


class Event(Base):
    __tablename__ = "events"
    __table_args__ = {"extend_existing": True}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(Enum(EventType), nullable=False)
    sim_date = Column(Date, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(JSON, nullable=True)


class SimulationConfig(Base):
    __tablename__ = "simulation_config"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, default=1)
    warehouse_capacity = Column(Integer, nullable=False, default=2200)
    daily_assembly_hours = Column(Float, nullable=False, default=8.0)
    assembly_lines = Column(Integer, nullable=False, default=1)
    workers_per_line = Column(Integer, nullable=False, default=1)
    shift_hours = Column(Float, nullable=False, default=8.0)
    demand_distribution_mean = Column(Float, nullable=False, default=5.0)
    demand_distribution_variance = Column(Float, nullable=False, default=2.0)
    sim_date = Column(Date, nullable=False, default=date.today)
