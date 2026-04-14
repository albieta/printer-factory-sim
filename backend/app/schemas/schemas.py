from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


# Enums
class ProductType(str, Enum):
    PRINTER = "PRINTER"
    MATERIAL = "MATERIAL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    RELEASED = "RELEASED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class PurchaseOrderStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"


class EventType(str, Enum):
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_RELEASED = "ORDER_RELEASED"
    ORDER_BLOCKED_MATERIALS = "ORDER_BLOCKED_MATERIALS"
    ORDER_STARTED = "ORDER_STARTED"
    ORDER_COMPLETED = "ORDER_COMPLETED"
    PO_CREATED = "PO_CREATED"
    PO_DELIVERED = "PO_DELIVERED"
    PO_REJECTED_CAPACITY = "PO_REJECTED_CAPACITY"
    MATERIAL_CONSUMED = "MATERIAL_CONSUMED"
    INVENTORY_ADDED = "INVENTORY_ADDED"
    DAY_ADVANCED = "DAY_ADVANCED"
    PRODUCTION_BLOCKED_CAPACITY = "PRODUCTION_BLOCKED_CAPACITY"


# Product Schemas
class ProductBase(BaseModel):
    name: str
    type: ProductType
    assembly_hours: Optional[float] = None


class ProductCreate(ProductBase):
    pass


class Product(ProductBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


# BOM Schemas
class BOMBase(BaseModel):
    finished_product_id: str
    material_id: str
    quantity: float


class BOMCreate(BOMBase):
    pass


class BOMEntry(BOMBase):
    id: str

    class Config:
        from_attributes = True


# Supplier Schemas
class SupplierBase(BaseModel):
    name: str
    product_id: str
    unit_cost: float
    lead_time_days: int
    quantity_breaks: Optional[List[dict]] = None


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    unit_cost: Optional[float] = None
    lead_time_days: Optional[int] = None
    quantity_breaks: Optional[List[dict]] = None


class Supplier(SupplierBase):
    id: str

    class Config:
        from_attributes = True


# Inventory Schemas
class InventoryBase(BaseModel):
    product_id: str
    quantity: float


class InventoryLevel(InventoryBase):
    last_updated: datetime

    class Config:
        from_attributes = True


class CapacityInfo(BaseModel):
    warehouse_capacity: int
    current_usage: float
    available_capacity: float
    usage_percentage: float


class ManualAdjust(BaseModel):
    product_id: str
    quantity: float  # Positive to add, negative to subtract


# Manufacturing Order Schemas
class ManufacturingOrderBase(BaseModel):
    product_id: str
    quantity: int


class ManufacturingOrder(ManufacturingOrderBase):
    id: str
    status: OrderStatus
    created_date: date
    released_date: Optional[date] = None
    completed_date: Optional[date] = None

    class Config:
        from_attributes = True


class ManufacturingOrderDetail(ManufacturingOrder):
    product_name: Optional[str] = None
    bom_requirements: Optional[List[dict]] = None


class ReleaseRequest(BaseModel):
    order_ids: List[str]


class BatchReleaseResponse(BaseModel):
    successful: List[str]
    failed: List[dict]  # {order_id: str, reason: str}


class BOMRequirements(BaseModel):
    product_id: str
    product_name: str
    requirements: List[dict]  # [{material_id, material_name, quantity_per_unit, total_required}]


# Purchase Order Schemas
class PurchaseOrderCreate(BaseModel):
    supplier_id: str
    product_id: str
    quantity: int


class PurchaseOrder(PurchaseOrderCreate):
    id: str
    issue_date: date
    expected_delivery: date
    actual_delivery: Optional[date] = None
    status: PurchaseOrderStatus
    unit_cost: float

    class Config:
        from_attributes = True


class PurchaseOrderDetail(PurchaseOrder):
    supplier_name: Optional[str] = None
    product_name: Optional[str] = None


# Event Schemas
class EventBase(BaseModel):
    event_type: EventType
    sim_date: date
    details: Optional[dict] = None


class Event(EventBase):
    id: str
    timestamp: datetime

    class Config:
        from_attributes = True


class TimeSeriesData(BaseModel):
    metric: str
    data_points: List[dict]  # [{date, value}]


# Simulation Config Schemas
class SimulationConfigBase(BaseModel):
    warehouse_capacity: int = 1000
    daily_assembly_hours: float = 8.0
    demand_distribution_mean: float = 5.0
    demand_distribution_variance: float = 2.0


class SimulationConfigUpdate(SimulationConfigBase):
    pass


class SimulationConfig(SimulationConfigBase):
    id: int
    sim_date: date

    class Config:
        from_attributes = True


class PrinterModel(BaseModel):
    id: str
    name: str
    assembly_hours: float


class PrinterModelCreate(BaseModel):
    name: str
    assembly_hours: float


class Material(BaseModel):
    id: str
    name: str


class MaterialCreate(BaseModel):
    name: str


# Simulation Status
class SimulationStatus(BaseModel):
    current_date: date
    pending_orders: int
    completed_orders: int
    inventory_items: int
    total_events: int


class DayAdvanceResult(BaseModel):
    sim_date: date
    events_generated: int
    orders_created: int
    orders_completed: int
    purchase_orders_delivered: int


class ResetConfirm(BaseModel):
    success: bool
    message: str


class ImportResult(BaseModel):
    success: bool
    message: str
    errors: Optional[List[str]] = None
