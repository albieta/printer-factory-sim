import axios from 'axios';
import type {
  AdvanceAllResult,
  SimulationConfig,
  SimulationStatus,
  DayAdvanceResult,
  ManufacturingOrder,
  PurchaseOrder,
  InventoryLevel,
  CapacityInfo,
  Supplier,
  Product,
  BOMEntry,
  Event,
  BatchReleaseResponse,
  ReleaseRequest,
  TimeSeriesData,
  ManualAdjust,
  BOMRequirements,
  ImportResult,
  ScenarioListResponse,
  ScenarioStatusResponse,
  ScenarioRunRecord,
  ScenarioStartRequest,
  LogFile,
  LogContents,
  MetricsSnapshot,
} from '../types';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const getErrorMessage = (error: unknown, fallback: string) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
  }
  return fallback;
};

export const configAPI = {
  getConfig: () => api.get<SimulationConfig>('/config/'),
  updateConfig: (config: Partial<SimulationConfig>) => api.put<SimulationConfig>('/config/', config),
  getPrinterModels: () => api.get<Product[]>('/config/printer-models/'),
  createPrinterModel: (printer: { name: string; assembly_hours: number }) =>
    api.post<Product>('/config/printer-models/', printer),
  deletePrinterModel: (id: string) => api.delete(`/config/printer-models/${id}/`),
  applyScenarioAssembly: (assembly: any) => api.post<SimulationConfig>('/config/apply-scenario-assembly', assembly),
  applyScenarioCosts: (costs: any) => api.post<SimulationConfig>('/config/apply-scenario-costs', costs),
  openLine: () => api.post<SimulationConfig>('/config/assembly/open-line'),
  closeLine: () => api.post<SimulationConfig>('/config/assembly/close-line'),
  hireWorker: () => api.post<SimulationConfig>('/config/assembly/hire-worker'),
  fireWorker: () => api.post<SimulationConfig>('/config/assembly/fire-worker'),
};

export const materialsAPI = {
  getMaterials: () => api.get<Product[]>('/materials/'),
  createMaterial: (material: { name: string }) => api.post<Product>('/materials/', material),
  getBOM: () => api.get<BOMEntry[]>('/materials/bom/'),
  createBOM: (bom: { finished_product_id: string; material_id: string; quantity: number }) =>
    api.post<BOMEntry>('/materials/bom/', bom),
  deleteBOM: (id: string) => api.delete(`/materials/bom/${id}/`),
};

export const suppliersAPI = {
  getSuppliers: () => api.get<Supplier[]>('/suppliers/'),
  createSupplier: (supplier: Omit<Supplier, 'id'>) => api.post<Supplier>('/suppliers/', supplier),
  updateSupplier: (id: string, updates: Partial<Supplier>) => api.put<Supplier>(`/suppliers/${id}/`, updates),
  deleteSupplier: (id: string) => api.delete(`/suppliers/${id}/`),
};

export const providersAPI = {
  getProviders: () => api.get('/providers/'),
  getProviderCatalog: (name: string) => api.get(`/providers/${encodeURIComponent(name)}/catalog`),
  getProviderStock: (name: string) => api.get(`/providers/${encodeURIComponent(name)}/stock`),
  getProviderOrders: (name: string) => api.get(`/providers/${encodeURIComponent(name)}/orders`),
  updateProviderUrl: (name: string, url: string) =>
    api.put(`/providers/${encodeURIComponent(name)}/url`, { url }),
};

export interface RetailerSummary {
  available: boolean;
  current_day: number;
  fulfilled_count: number;
  backordered_count: number;
  total_revenue: number;
}

export interface RetailerStock {
  available: boolean;
  schema_version?: number;
  items?: Array<{ product_name: string; quantity: number }>;
}

export interface RetailerOrder {
  id: number;
  customer?: string;
  product_name?: string;
  quantity: number;
  status: string;
  placed_day?: number;
  fulfilled_day?: number;
  total_price?: number;
}

export interface RetailerPurchaseOrder {
  id: number;
  product_name?: string;
  quantity: number;
  status: string;
  placed_day?: number;
  expected_delivery_day?: number;
  delivered_day?: number;
}

export const retailerAPI = {
  getSummary: () => api.get<RetailerSummary>('/retailer/summary'),
  getStock: () => api.get<RetailerStock>('/retailer/stock'),
  placePurchase: (payload: { product_name: string; quantity: number }) =>
    api.post<{ order: RetailerPurchaseOrder }>('/retailer/purchases', payload),
  getOrders: (status?: string) =>
    api.get<{ available: boolean; orders: RetailerOrder[] }>('/retailer/orders', {
      params: status ? { status } : {},
    }),
  getPurchases: () => api.get<{ available: boolean; purchases: RetailerPurchaseOrder[] }>('/retailer/purchases'),
};

export const inventoryAPI = {
  getInventory: () => api.get<InventoryLevel[]>('/inventory/'),
  getCapacity: () => api.get<CapacityInfo>('/inventory/capacity/'),
  manualAdjust: (adjust: ManualAdjust) => api.post<InventoryLevel>('/inventory/manual-adjust/', adjust),
};

export const ordersAPI = {
  getManufacturingOrders: (status?: string) =>
    api.get<ManufacturingOrder[]>('/orders/mfg/', { params: status ? { status } : {} }),
  getManufacturingOrder: (id: string) => api.get<ManufacturingOrder>(`/orders/mfg/${id}/`),
  getOrderRequirements: (id: string) => api.get<BOMRequirements>(`/orders/mfg/${id}/requirements/`),
  releaseOrders: (request: ReleaseRequest) => api.post<BatchReleaseResponse>('/orders/mfg/release', request),
  rejectOrders: (request: ReleaseRequest) => api.post<BatchReleaseResponse>('/orders/mfg/reject', request),
};

export interface SalesOrder {
  id: string;
  reference_code: string;
  retailer: string;
  model: string | null;
  quantity: number;
  unit_price: string;
  total_price: string;
  placed_day: number;
  expected_ship_day: number | null;
  status: string;
  status_reason: string | null;
}

export const salesOrdersAPI = {
  list: (status?: string) =>
    api.get<SalesOrder[]>('/sales/orders', { params: status ? { status } : {} }),
  release: (id: string) =>
    api.post<{ schema_version: number; order: SalesOrder }>(`/sales/orders/${id}/release`),
  reject: (id: string, reason = '') =>
    api.post<{ schema_version: number; order: SalesOrder }>(`/sales/orders/${id}/reject`, { reason }),
};

export const purchaseOrdersAPI = {
  getPurchaseOrders: () => api.get<PurchaseOrder[]>('/orders/purchase/'),
  createPurchaseOrder: (po: { supplier_id: string; product_id: string; quantity: number }) =>
    api.post<PurchaseOrder>('/orders/purchase/', po),
};

export const simulationAPI = {
  getStatus: () => api.get<SimulationStatus>('/simulation/status/'),
  advanceDay: () => api.post<DayAdvanceResult>('/simulation/advance-day/'),
  advanceAll: () => api.post<AdvanceAllResult>('/simulation/advance-all'),
  reset: () => api.post<{ success: boolean; message: string }>('/simulation/reset/'),
  resetToEmpty: () => api.post<{ success: boolean; message: string }>('/simulation/reset-empty/'),
  resetToDefaultConfig: () => api.post<{ success: boolean; message: string }>('/simulation/reset-default-config/'),
};

export const eventsAPI = {
  getEvents: (params?: { type?: string; from_date?: string; to_date?: string; limit?: number }) => api.get<Event[]>('/events/', { params }),
  getTimeSeries: (metric: string, params?: { from_date?: string; to_date?: string }) =>
    api.get<TimeSeriesData>(`/events/timeseries/${metric}`, { params }),
};

export const exportAPI = {
  exportFullState: () => api.get('/export/full-state/'),
  exportInventory: () => api.get('/export/inventory-only/'),
  exportEvents: () => api.get('/export/events-only/'),
  importFullState: (payload: unknown) => api.post<ImportResult>('/import/full-state/', payload),
};

export const scenariosAPI = {
  list: () => api.get<ScenarioListResponse>('/scenarios/'),
  status: () => api.get<ScenarioStatusResponse>('/scenarios/status'),
  start: (payload: ScenarioStartRequest) => api.post<ScenarioRunRecord>('/scenarios/start', payload),
  stop: () => api.post<{ stopped: boolean; reason?: string }>('/scenarios/stop'),
  listLogs: () => api.get<{ files: LogFile[] }>('/scenarios/logs'),
  readLog: (name: string, maxBytes = 64 * 1024) =>
    api.get<LogContents>(`/scenarios/logs/${encodeURIComponent(name)}`, { params: { max_bytes: maxBytes } }),
  metrics: (limit = 100) => api.get<{ snapshots: MetricsSnapshot[] }>('/scenarios/metrics', { params: { limit } }),
  clearLogs: () => api.post<{ deleted: number }>('/scenarios/logs/clear'),
};

export interface FinancialSummary {
  total_costs: number;
  total_revenue: number;
  net_profit: number;
  cost_per_assembly_line: number;
  cost_per_assembly_line_per_day: number;
  cost_per_worker_per_hour: number;
  max_workers_per_line: number;
}

export interface FinancialTransaction {
  type: string;
  amount: number;
  description: string;
  sim_day: number;
}

export const financialAPI = {
  getSummary: () => api.get<FinancialSummary>('/financial/summary'),
  getConfig: () => api.get<SimulationConfig>('/financial/config'),
  updateConfig: (config: Partial<SimulationConfig>) => api.put<SimulationConfig>('/financial/config', config),
  getTransactions: (day?: number) =>
    api.get<FinancialTransaction[]>('/financial/transactions', { params: day ? { day } : {} }),
};

export default api;
