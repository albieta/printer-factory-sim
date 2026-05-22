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
  PO_REJECTED = 'PO_REJECTED',
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
  external_provider_url?: string | null;
  external_product_id?: number | null;
}

export interface InventoryLevel {
  product_id: string;
  product_name?: string;
  quantity: number;
  last_updated: string;
  accepted_order_demand: number;
  pending_inbound_quantity: number;
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
  external_order_id?: number | null;
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

export interface ImportResult {
  success: boolean;
  message: string;
  errors?: string[];
}

// ── Scenario runner (Week 8) ────────────────────────────────────────────────
export interface ScenarioEvent {
  name: string | null;
  start_day: number | null;
  end_day: number | null;
  description: string | null;
}

export interface ScenarioSummary {
  name: string;
  relative_path: string;
  kind: 'scenario';
  scenario_name?: string | null;
  event_count?: number;
  events?: ScenarioEvent[];
}

export interface ConfigSummary {
  name: string;
  relative_path: string;
  kind: 'config';
  retailers?: Array<string | null>;
  manufacturer?: string | null;
  providers?: Array<string | null>;
  uses_skills?: boolean;
}

export interface ScenarioListResponse {
  scenarios: ScenarioSummary[];
  configs: ConfigSummary[];
}

export interface ScenarioRunRecord {
  run_id: string;
  config: string;
  scenario: string;
  days: number;
  started_at: string;
  status: 'running' | 'stopping' | 'completed' | 'failed';
  finished_at: string | null;
  exit_code: number | null;
  stdout_lines: string[];
  log_file: string | null;
  current_day: number;
}

export interface ScenarioStatusResponse {
  active: boolean;
  run: ScenarioRunRecord | null;
}

export interface ScenarioStartRequest {
  config: string;
  scenario: string;
  days: number;
  model?: string;
  thinking_enabled?: boolean;
}

export interface LogFile {
  name: string;
  size: number;
  modified: string;
}

export interface LogContents {
  name: string;
  exists: boolean;
  size?: number;
  truncated?: boolean;
  content: string;
}

export interface MetricsSnapshot {
  ts: string;
  scenario: string;
  day: number;
  signal: Record<string, unknown>;
  retailers: Array<{
    name: string;
    stock: Record<string, number>;
    prices: Record<string, number>;
    customer_orders: {
      status_counts: Record<string, number>;
      placed_today: number;
      fulfilled_today: number;
      backordered_today: number;
      cancelled_today: number;
    };
    purchases: Record<string, number>;
    errors: string[];
  }>;
  manufacturer: {
    name: string;
    inventory: Record<string, number>;
    prices: Record<string, number>;
    sales_orders: Record<string, number>;
    active_production_orders: number;
    capacity: Record<string, unknown>;
    errors: string[];
  };
  providers: Array<{
    name: string;
    stock: Record<string, number>;
    prices: Record<string, Record<string, number>>;
    orders: Record<string, number>;
    errors: string[];
  }>;
}
