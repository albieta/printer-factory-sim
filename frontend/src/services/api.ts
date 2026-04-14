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
  BOMRequirements
} from '../types';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Configuration endpoints
export const configAPI = {
  getConfig: () => api.get<SimulationConfig>('/config/'),
  updateConfig: (config: Partial<SimulationConfig>) => api.put<SimulationConfig>('/config/', config),
  getPrinterModels: () => api.get<Product[]>('/config/printer-models/'),
  createPrinterModel: (printer: {name: string; assembly_hours: number}) => 
    api.post<Product>('/config/printer-models/', printer),
  deletePrinterModel: (id: string) => api.delete(`/config/printer-models/${id}/`),
};

// Materials & BOM endpoints
export const materialsAPI = {
  getMaterials: () => api.get<Product[]>('/materials/'),
  createMaterial: (material: {name: string}) => api.post<Product>('/materials/', material),
  getBOM: () => api.get<BOMEntry[]>('/materials/bom/'),
  createBOM: (bom: {finished_product_id: string; material_id: string; quantity: number}) => 
    api.post<BOMEntry>('/materials/bom/', bom),
  deleteBOM: (id: string) => api.delete(`/materials/bom/${id}/`),
};

// Supplier endpoints
export const suppliersAPI = {
  getSuppliers: () => api.get<Supplier[]>('/suppliers/'),
  createSupplier: (supplier: Omit<Supplier, 'id'>) => api.post<Supplier>('/suppliers/', supplier),
  updateSupplier: (id: string, updates: Partial<Supplier>) => 
    api.put<Supplier>(`/suppliers/${id}/`, updates),
  deleteSupplier: (id: string) => api.delete(`/suppliers/${id}/`),
};

// Inventory endpoints
export const inventoryAPI = {
  getInventory: () => api.get<InventoryLevel[]>('/inventory/'),
  getCapacity: () => api.get<CapacityInfo>('/inventory/capacity/'),
  manualAdjust: (adjust: ManualAdjust) => 
    api.post<InventoryLevel>('/inventory/manual-adjust/', adjust),
};

// Manufacturing Order endpoints
export const ordersAPI = {
  getManufacturingOrders: (status?: string) => 
    api.get<ManufacturingOrder[]>('/orders/mfg/', {params: status ? {status} : {}}),
  getManufacturingOrder: (id: string) => 
    api.get<ManufacturingOrder>(`/orders/mfg/${id}/`),
  getOrderRequirements: (id: string) => 
    api.get<BOMRequirements>(`/orders/mfg/${id}/requirements/`),
  releaseOrders: (request: ReleaseRequest) => 
    api.post<BatchReleaseResponse>('/orders/mfg/release/', request),
};

// Purchase Order endpoints
export const purchaseOrdersAPI = {
  getPurchaseOrders: () => api.get<PurchaseOrder[]>('/orders/purchase/'),
  createPurchaseOrder: (po: {supplier_id: string; product_id: string; quantity: number}) => 
    api.post<PurchaseOrder>('/orders/purchase/', po),
};

// Simulation endpoints
export const simulationAPI = {
  getStatus: () => api.get<SimulationStatus>('/simulation/status/'),
  advanceDay: () => api.post<DayAdvanceResult>('/simulation/advance-day/'),
  reset: () => api.post<{success: boolean; message: string}>('/simulation/reset/'),
};

// Event endpoints
export const eventsAPI = {
  getEvents: (params?: {type?: string; from_date?: string; to_date?: string; limit?: number}) => 
    api.get<Event[]>('/events/', {params}),
  getTimeSeries: (metric: string, params?: {from_date?: string; to_date?: string}) => 
    api.get<TimeSeriesData>(`/events/timeseries/${metric}`, {params}),
};

// Export endpoints
export const exportAPI = {
  exportFullState: () => api.get('/export/full-state/'),
  exportInventory: () => api.get('/export/inventory-only/'),
  exportEvents: () => api.get('/export/events-only/'),
};

export default api;
