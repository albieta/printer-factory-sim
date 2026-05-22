import axios from 'axios';
import type {
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

export const purchaseOrdersAPI = {
  getPurchaseOrders: () => api.get<PurchaseOrder[]>('/orders/purchase/'),
  createPurchaseOrder: (po: { supplier_id: string; product_id: string; quantity: number }) =>
    api.post<PurchaseOrder>('/orders/purchase/', po),
};

export const simulationAPI = {
  getStatus: () => api.get<SimulationStatus>('/simulation/status/'),
  advanceDay: () => api.post<DayAdvanceResult>('/simulation/advance-day/'),
  reset: () => api.post<{ success: boolean; message: string }>('/simulation/reset/'),
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

export default api;
