from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class ProductType(str, Enum):
    PRINTER = "PRINTER"
    MATERIAL = "MATERIAL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    RELEASED = "RELEASED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


class PurchaseOrderStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"


class EventType(str, Enum):
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
    SALES_ORDER_SHIPPED = "SALES_ORDER_SHIPPED"
    SALES_ORDER_DELIVERED = "SALES_ORDER_DELIVERED"
    WHOLESALE_PRICE_CHANGED = "WHOLESALE_PRICE_CHANGED"


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


class SupplierBase(BaseModel):
    name: str
    product_id: str
    unit_cost: float
    lead_time_days: int
    quantity_breaks: Optional[list[dict[str, Any]]] = None
    external_provider_url: Optional[str] = None
    external_product_id: Optional[int] = None


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    unit_cost: Optional[float] = None
    lead_time_days: Optional[int] = None
    quantity_breaks: Optional[list[dict[str, Any]]] = None
    external_provider_url: Optional[str] = None
    external_product_id: Optional[int] = None


class Supplier(SupplierBase):
    id: str
    product_name: Optional[str] = None

    class Config:
        from_attributes = True


class InventoryBase(BaseModel):
    product_id: str
    quantity: float


class InventoryLevel(InventoryBase):
    last_updated: Optional[datetime] = None
    product_name: Optional[str] = None
    accepted_order_demand: float = 0.0
    pending_inbound_quantity: float = 0.0

    class Config:
        from_attributes = True


class CapacityInfo(BaseModel):
    warehouse_capacity: int
    current_usage: float
    available_capacity: float
    usage_percentage: float
    assembly_lines: int
    workers_per_line: int
    daily_assembly_hours: float


class ManualAdjust(BaseModel):
    product_id: str
    quantity: float


class ManufacturingOrderBase(BaseModel):
    product_id: str
    quantity: int


class ManufacturingOrder(ManufacturingOrderBase):
    id: str
    reference_code: Optional[str] = None
    product_name: Optional[str] = None
    status: OrderStatus
    status_label: Optional[str] = None
    status_reason: Optional[str] = None
    created_date: date
    released_date: Optional[date] = None
    completed_date: Optional[date] = None

    class Config:
        from_attributes = True


class ManufacturingOrderDetail(ManufacturingOrder):
    bom_requirements: Optional[list[dict[str, Any]]] = None


class ReleaseRequest(BaseModel):
    order_ids: list[str]


class BatchReleaseResponse(BaseModel):
    successful: list[str]
    failed: list[dict[str, Any]]


class BOMRequirements(BaseModel):
    product_id: str
    product_name: str
    requirements: list[dict[str, Any]]


class PurchaseOrderCreate(BaseModel):
    supplier_id: str
    product_id: str
    quantity: int


class PurchaseOrder(BaseModel):
    id: str
    reference_code: Optional[str] = None
    supplier_id: str
    supplier_name: Optional[str] = None
    product_id: str
    product_name: Optional[str] = None
    quantity: int
    issue_date: date
    expected_delivery: date
    actual_delivery: Optional[date] = None
    status: PurchaseOrderStatus
    status_label: Optional[str] = None
    status_reason: Optional[str] = None
    unit_cost: float
    total_cost: float
    external_order_id: Optional[int] = None

    class Config:
        from_attributes = True


class PurchaseOrderDetail(PurchaseOrder):
    pass


class EventBase(BaseModel):
    event_type: EventType
    sim_date: date
    details: Optional[dict[str, Any]] = None


class Event(EventBase):
    id: str
    timestamp: datetime

    class Config:
        from_attributes = True


class TimeSeriesData(BaseModel):
    metric: str
    data_points: list[dict[str, Any]]


class SimulationConfigBase(BaseModel):
    warehouse_capacity: int = 2200
    daily_assembly_hours: float = 8.0
    assembly_lines: int = 1
    workers_per_line: int = 1
    shift_hours: float = 8.0
    demand_distribution_mean: float = 5.0
    demand_distribution_variance: float = 2.0
    internal_demand_enabled: bool = False
    cost_per_assembly_line: float = 50000.0
    cost_per_assembly_line_per_day: float = 100.0
    cost_per_worker_per_hour: float = 50.0
    max_workers_per_line: int = 10
    retailer_demand_enabled: bool = False
    retailer_demand_mean: float = 8.0
    retailer_demand_variance: float = 2.0
    retailer_demand_modifier: float = 1.0
    retailer_demand_base_price: float = 400.0


class SimulationConfigUpdate(SimulationConfigBase):
    pass


class SimulationConfig(SimulationConfigBase):
    id: int
    sim_date: date
    sim_day: int = 0
    effective_daily_assembly_hours: float
    total_costs: float = 0.0
    total_revenue: float = 0.0
    provider_urls: Optional[Any] = None

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


class WorkflowStage(BaseModel):
    key: str
    label: str
    route: str
    description: str
    value: str


class SimulationStatus(BaseModel):
    current_date: date
    pending_orders: int
    released_orders: int
    blocked_orders: int
    completed_orders: int
    rejected_orders: int
    pending_purchase_orders: int
    delivered_purchase_orders: int
    rejected_purchase_orders: int
    inventory_items: int
    total_events: int
    warehouse_capacity: int
    current_usage: float
    available_capacity: float
    usage_percentage: float
    assembly_lines: int
    workers_per_line: int
    shift_hours: float
    effective_daily_assembly_hours: float
    workflow_stages: list[WorkflowStage]


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
    errors: Optional[list[str]] = None


class FinancialSummary(BaseModel):
    total_costs: float
    total_revenue: float
    net_profit: float
    cost_per_assembly_line: float
    cost_per_assembly_line_per_day: float
    cost_per_worker_per_hour: float
    max_workers_per_line: int

    class Config:
        from_attributes = True


class ProviderUrlUpdate(BaseModel):
    url: str = ""
