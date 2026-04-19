export enum ProductType {
  PRINTER = 'PRINTER',
  MATERIAL = 'MATERIAL',
}

export enum OrderStatus {
  PENDING = 'PENDING',
  RELEASED = 'RELEASED',
  COMPLETED = 'COMPLETED',
  BLOCKED = 'BLOCKED',
  REJECTED = 'REJECTED',
}

export enum PurchaseOrderStatus {
  PENDING = 'PENDING',
  DELIVERED = 'DELIVERED',
  REJECTED = 'REJECTED',
}

export enum EventType {
  ORDER_CREATED = 'ORDER_CREATED',
  ORDER_RELEASED = 'ORDER_RELEASED',
  ORDER_BLOCKED_MATERIALS = 'ORDER_BLOCKED_MATERIALS',
  ORDER_UNBLOCKED_MATERIALS = 'ORDER_UNBLOCKED_MATERIALS',
  ORDER_REJECTED = 'ORDER_REJECTED',
  ORDER_STARTED = 'ORDER_STARTED',
  ORDER_COMPLETED = 'ORDER_COMPLETED',
  PO_CREATED = 'PO_CREATED',
  PO_DELIVERED = 'PO_DELIVERED',
  PO_REJECTED_CAPACITY = 'PO_REJECTED_CAPACITY',
  MATERIAL_CONSUMED = 'MATERIAL_CONSUMED',
  INVENTORY_ADDED = 'INVENTORY_ADDED',
  DAY_ADVANCED = 'DAY_ADVANCED',
  PRODUCTION_BLOCKED_CAPACITY = 'PRODUCTION_BLOCKED_CAPACITY',
}

export interface Product {
  id: string;
  name: string;
  type: ProductType;
  assembly_hours?: number;
  created_at: string;
}

export interface BOMEntry {
  id: string;
  finished_product_id: string;
  material_id: string;
  quantity: number;
}

export interface Supplier {
  id: string;
  name: string;
  product_id: string;
  product_name?: string;
  unit_cost: number;
  lead_time_days: number;
  quantity_breaks?: Array<{ qty: number; price: number }>;
}

export interface InventoryLevel {
  product_id: string;
  product_name?: string;
  quantity: number;
  last_updated: string;
  accepted_order_demand: number;
}

export interface CapacityInfo {
  warehouse_capacity: number;
  current_usage: number;
  available_capacity: number;
  usage_percentage: number;
}

export interface ManufacturingOrder {
  id: string;
  reference_code?: string;
  product_id: string;
  product_name?: string;
  quantity: number;
  status: OrderStatus;
  status_label?: string;
  status_reason?: string | null;
  created_date: string;
  released_date?: string;
  completed_date?: string;
}

export interface PurchaseOrder {
  id: string;
  reference_code?: string;
  supplier_id: string;
  supplier_name?: string;
  product_id: string;
  product_name?: string;
  quantity: number;
  issue_date: string;
  expected_delivery: string;
  actual_delivery?: string;
  status: PurchaseOrderStatus;
  status_label?: string;
  status_reason?: string | null;
  unit_cost: number;
  total_cost: number;
}

export interface Event {
  id: string;
  event_type: EventType;
  sim_date: string;
  timestamp: string;
  details?: Record<string, unknown>;
}

export interface WorkflowStage {
  key: string;
  label: string;
  route: string;
  description: string;
  value: string;
}

export interface SimulationConfig {
  id?: number;
  warehouse_capacity: number;
  daily_assembly_hours: number;
  assembly_lines: number;
  workers_per_line: number;
  shift_hours: number;
  effective_daily_assembly_hours: number;
  demand_distribution_mean: number;
  demand_distribution_variance: number;
  sim_date?: string;
}

export interface SimulationStatus {
  current_date: string;
  pending_orders: number;
  released_orders: number;
  blocked_orders: number;
  completed_orders: number;
  rejected_orders: number;
  pending_purchase_orders: number;
  delivered_purchase_orders: number;
  rejected_purchase_orders: number;
  inventory_items: number;
  total_events: number;
  warehouse_capacity: number;
  current_usage: number;
  available_capacity: number;
  usage_percentage: number;
  assembly_lines: number;
  workers_per_line: number;
  shift_hours: number;
  effective_daily_assembly_hours: number;
  workflow_stages: WorkflowStage[];
}

export interface DayAdvanceResult {
  sim_date: string;
  events_generated: number;
  orders_created: number;
  orders_completed: number;
  purchase_orders_delivered: number;
}

export interface BOMRequirements {
  product_id: string;
  product_name: string;
  requirements: Array<{
    material_id: string;
    material_name: string;
    quantity_per_unit: number;
    total_required: number;
  }>;
}

export interface ReleaseRequest {
  order_ids: string[];
}

export interface BatchReleaseResponse {
  successful: string[];
  failed: Array<{ order_id: string; reason: string }>;
}

export interface TimeSeriesData {
  metric: string;
  data_points: Array<{ date: string; value: unknown }>;
}

export interface ManualAdjust {
  product_id: string;
  quantity: number;
}
