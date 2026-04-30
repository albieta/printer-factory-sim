import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Table } from 'react-bootstrap';
import { FaPlus, FaShoppingCart, FaTrash } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import { getErrorMessage, materialsAPI, purchaseOrdersAPI, suppliersAPI } from '../services/api';
import type { Product, PurchaseOrder, Supplier } from '../types';
import { PurchaseOrderStatus } from '../types';
import { announceSimulationUpdate, onSimulationUpdate } from '../utils/simulationEvents';
import { formatCurrency } from '../utils/formatters';
import LoadingSpinner from '../components/LoadingSpinner';

const parseQuantityBreaks = (input: string) => {
  return input
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      const [qty, price] = entry.split(':').map((part) => part.trim());
      return { qty: Number(qty), price: Number(price) };
    })
    .filter((entry) => !Number.isNaN(entry.qty) && !Number.isNaN(entry.price))
    .sort((a, b) => a.qty - b.qty);
};

const getEffectiveUnitCost = (supplier: Supplier | null, quantity: number) => {
  if (!supplier || quantity <= 0) {
    return 0;
  }

  const tierPrice = [...(supplier.quantity_breaks ?? [])]
    .sort((a, b) => a.qty - b.qty)
    .reduce<number | null>((current, tier) => (quantity >= tier.qty ? Number(tier.price) : current), null);

  return tierPrice ?? Number(supplier.unit_cost);
};

const Suppliers: React.FC = () => {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [materials, setMaterials] = useState<Product[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingSupplier, setSavingSupplier] = useState(false);
  const [savingPo, setSavingPo] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [supplierForm, setSupplierForm] = useState({
    name: '',
    product_id: '',
    unit_cost: '0',
    lead_time_days: '1',
    quantity_breaks: '',
  });

  const [poForm, setPoForm] = useState({
    supplier_id: '',
    quantity: '100',
  });

  const loadData = async () => {
    try {
      setLoading(true);
      const [suppliersRes, materialsRes, poRes] = await Promise.all([
        suppliersAPI.getSuppliers(),
        materialsAPI.getMaterials(),
        purchaseOrdersAPI.getPurchaseOrders(),
      ]);
      setSuppliers(suppliersRes.data);
      setMaterials(materialsRes.data);
      setPurchaseOrders(poRes.data);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load supplier and purchasing data.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
    const clear = onSimulationUpdate(() => {
      void loadData();
    });

    return clear;
  }, []);

  const materialMap = useMemo(() => new Map(materials.map((material) => [material.id, material.name])), [materials]);
  const selectedSupplier = suppliers.find((supplier) => supplier.id === poForm.supplier_id) ?? null;
  const selectedQuantity = Number(poForm.quantity) || 0;
  const effectiveUnitCost = getEffectiveUnitCost(selectedSupplier, selectedQuantity);
  const totalCost = effectiveUnitCost * selectedQuantity;

  const createSupplier = async () => {
    try {
      setSavingSupplier(true);
      await suppliersAPI.createSupplier({
        name: supplierForm.name,
        product_id: supplierForm.product_id,
        unit_cost: Number(supplierForm.unit_cost),
        lead_time_days: Number(supplierForm.lead_time_days),
        quantity_breaks: parseQuantityBreaks(supplierForm.quantity_breaks),
      });
      setSupplierForm({ name: '', product_id: '', unit_cost: '0', lead_time_days: '1', quantity_breaks: '' });
      setMessage('Supplier created successfully.');
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to create supplier.'));
    } finally {
      setSavingSupplier(false);
    }
  };

  const deleteSupplier = async (supplierId: string) => {
    try {
      await suppliersAPI.deleteSupplier(supplierId);
      setMessage('Supplier removed.');
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to delete supplier.'));
    }
  };

  const createPurchaseOrder = async () => {
    if (!selectedSupplier) {
      return;
    }

    try {
      setSavingPo(true);
      await purchaseOrdersAPI.createPurchaseOrder({
        supplier_id: selectedSupplier.id,
        product_id: selectedSupplier.product_id,
        quantity: selectedQuantity,
      });
      setMessage(`Purchase order created at ${formatCurrency(effectiveUnitCost)} per unit, total ${formatCurrency(totalCost)}.`);
      announceSimulationUpdate();
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to create purchase order.'));
    } finally {
      setSavingPo(false);
    }
  };

  const purchaseSummary = useMemo(() => {
    const pending = purchaseOrders.filter((order) => order.status === PurchaseOrderStatus.PENDING).length;
    const delivered = purchaseOrders.filter((order) => order.status === PurchaseOrderStatus.DELIVERED).length;
    const rejected = purchaseOrders.filter((order) => order.status === PurchaseOrderStatus.REJECTED).length;
    const spend = purchaseOrders.reduce((total, order) => total + order.total_cost, 0);
    return { pending, delivered, rejected, spend };
  }, [purchaseOrders]);

  if (loading) {
    return <LoadingSpinner label="Loading suppliers and purchasing..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Procurement</div>
          <h1>Replenish materials before the line starves</h1>
          <p>Manage supplier pricing, create purchase orders, and understand how lead time, quantity breaks, and warehouse capacity shape material flow back into inventory.</p>
        </div>
      </div>

      <PageGuide
        title="Procurement"
        controls="This screen decides how materials are replenished. Supplier pricing can change with quantity breaks, and every purchase order enters transit with the chosen lead time."
        next="When the simulation advances, eligible purchase orders try to deliver into Inventory. If receiving them would exceed warehouse capacity, the receipt is rejected by the warehouse, not by the supplier."
        tip="Watch the live pricing preview before issuing a purchase order so the quantity, unit cost, and committed spend all make sense together."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}
      <Alert variant="info">
        Purchase-order rejections mean the warehouse could not receive the incoming material on delivery day because storage would have exceeded the configured capacity.
      </Alert>

      <div className="kpi-grid">
        <div className="kpi-card info">
          <div className="kpi-label">Suppliers</div>
          <div className="kpi-value">{suppliers.length}</div>
          <div className="kpi-subtext">Active replenishment sources</div>
        </div>
        <div className="kpi-card warning">
          <div className="kpi-label">In Transit</div>
          <div className="kpi-value">{purchaseSummary.pending}</div>
          <div className="kpi-subtext">Purchase orders on the way to the warehouse</div>
        </div>
        <div className="kpi-card success">
          <div className="kpi-label">Received</div>
          <div className="kpi-value">{purchaseSummary.delivered}</div>
          <div className="kpi-subtext">Purchase orders delivered into stock</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Committed Spend</div>
          <div className="kpi-value">{formatCurrency(purchaseSummary.spend)}</div>
          <div className="kpi-subtext">Recorded purchase-order value</div>
        </div>
      </div>

      <div className="two-column">
        <Card>
          <Card.Header><FaPlus className="me-2" />Add supplier</Card.Header>
          <Card.Body>
            <Form.Group className="mb-3">
              <Form.Label>Supplier name</Form.Label>
              <Form.Control value={supplierForm.name} onChange={(event) => setSupplierForm({ ...supplierForm, name: event.target.value })} />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Material</Form.Label>
              <Form.Select value={supplierForm.product_id} onChange={(event) => setSupplierForm({ ...supplierForm, product_id: event.target.value })}>
                <option value="">Select a material</option>
                {materials.map((material) => (
                  <option key={material.id} value={material.id}>{material.name}</option>
                ))}
              </Form.Select>
            </Form.Group>
            <div className="two-column compact-grid">
              <Form.Group className="mb-3">
                <Form.Label>Base unit cost</Form.Label>
                <Form.Control type="number" min="0" step="0.01" value={supplierForm.unit_cost} onChange={(event) => setSupplierForm({ ...supplierForm, unit_cost: event.target.value })} />
              </Form.Group>
              <Form.Group className="mb-3">
                <Form.Label>Lead time (days)</Form.Label>
                <Form.Control type="number" min="1" step="1" value={supplierForm.lead_time_days} onChange={(event) => setSupplierForm({ ...supplierForm, lead_time_days: event.target.value })} />
              </Form.Group>
            </div>
            <Form.Group className="mb-3">
              <Form.Label>Quantity breaks</Form.Label>
              <Form.Control
                value={supplierForm.quantity_breaks}
                onChange={(event) => setSupplierForm({ ...supplierForm, quantity_breaks: event.target.value })}
                placeholder="100:9.50, 500:8.75"
              />
              <Form.Text>Optional tier pricing in the form <span className="mono">quantity:price</span>, comma separated.</Form.Text>
            </Form.Group>
            <Button variant="primary" onClick={createSupplier} disabled={savingSupplier || !supplierForm.name || !supplierForm.product_id}>
              {savingSupplier ? 'Saving supplier...' : 'Create supplier'}
            </Button>
          </Card.Body>
        </Card>

        <Card>
          <Card.Header><FaShoppingCart className="me-2" />Create purchase order</Card.Header>
          <Card.Body>
            <Form.Group className="mb-3">
              <Form.Label>Supplier</Form.Label>
              <Form.Select value={poForm.supplier_id} onChange={(event) => setPoForm({ ...poForm, supplier_id: event.target.value })}>
                <option value="">Select supplier</option>
                {suppliers.map((supplier) => (
                  <option key={supplier.id} value={supplier.id}>
                    {supplier.name} - {supplier.product_name ?? materialMap.get(supplier.product_id) ?? supplier.product_id}
                  </option>
                ))}
              </Form.Select>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Order quantity</Form.Label>
              <Form.Control type="number" min="1" step="1" value={poForm.quantity} onChange={(event) => setPoForm({ ...poForm, quantity: event.target.value })} />
            </Form.Group>
            {selectedSupplier ? (
              <div className="metric-item mb-3">
                <div className="stat-row">
                  <span>Material</span>
                  <strong>{selectedSupplier.product_name ?? materialMap.get(selectedSupplier.product_id) ?? selectedSupplier.product_id}</strong>
                </div>
                <div className="stat-row mt-2">
                  <span>Lead time</span>
                  <strong>{selectedSupplier.lead_time_days} days</strong>
                </div>
                <div className="stat-row mt-2">
                  <span>Effective unit cost</span>
                  <strong>{formatCurrency(effectiveUnitCost)}</strong>
                </div>
                <div className="stat-row mt-2">
                  <span>Total committed cost</span>
                  <strong>{formatCurrency(totalCost)}</strong>
                </div>
                <div className="text-muted mt-2">
                  Tier pricing updates live as quantity changes. The actual PO stores the same unit cost and total cost shown here.
                </div>
              </div>
            ) : null}
            <Button variant="success" onClick={createPurchaseOrder} disabled={savingPo || !selectedSupplier || selectedQuantity <= 0}>
              {savingPo ? 'Creating PO...' : 'Create purchase order'}
            </Button>
          </Card.Body>
        </Card>
      </div>

      <div className="card">
        <div className="card-header">Supplier roster</div>
        <div className="card-body p-0">
          {suppliers.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Material</th>
                  <th>Base Unit Cost</th>
                  <th>Lead Time</th>
                  <th>Pricing Tiers</th>
                  <th>Provider</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((supplier) => (
                  <tr key={supplier.id}>
                    <td><strong>{supplier.name}</strong></td>
                    <td>{supplier.product_name ?? materialMap.get(supplier.product_id) ?? supplier.product_id}</td>
                    <td>{formatCurrency(Number(supplier.unit_cost))}</td>
                    <td>{supplier.lead_time_days} days</td>
                    <td>
                      {supplier.quantity_breaks?.length ? supplier.quantity_breaks.map((tier) => (
                        <span key={`${tier.qty}-${tier.price}`} className="badge badge-neutral me-2">
                          {tier.qty}+ @ {formatCurrency(Number(tier.price))}
                        </span>
                      )) : <span className="text-muted">No tier pricing</span>}
                    </td>
                    <td>
                      {supplier.external_provider_url ? (
                        <span className="badge badge-info">External #{supplier.external_product_id ?? '-'}</span>
                      ) : (
                        <span className="text-muted">Local</span>
                      )}
                    </td>
                    <td>
                      <Button variant="outline-secondary" size="sm" onClick={() => void deleteSupplier(supplier.id)}>
                        <FaTrash className="me-2" />Delete
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">Create your first supplier to start replenishing raw materials.</div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">Purchase-order log</div>
        <div className="card-body p-0">
          {purchaseOrders.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Supplier</th>
                  <th>Material</th>
                  <th>Quantity</th>
                  <th>Unit Cost</th>
                  <th>Total Cost</th>
                  <th>Expected Delivery</th>
                  <th>Provider Order</th>
                  <th>Status</th>
                  <th>Status Reason</th>
                </tr>
              </thead>
              <tbody>
                {purchaseOrders.map((po) => (
                  <tr key={po.id}>
                    <td><span className="mono">{po.reference_code ?? po.id}</span></td>
                    <td>{po.supplier_name ?? po.supplier_id}</td>
                    <td>{po.product_name ?? po.product_id}</td>
                    <td>{po.quantity}</td>
                    <td>{formatCurrency(Number(po.unit_cost))}</td>
                    <td>{formatCurrency(po.total_cost)}</td>
                    <td>{po.expected_delivery}</td>
                    <td>{po.external_order_id ?? '-'}</td>
                    <td>
                      <span className={`badge ${po.status === PurchaseOrderStatus.DELIVERED ? 'badge-completed' : po.status === PurchaseOrderStatus.REJECTED ? 'badge-blocked' : 'badge-pending'}`}>
                        {po.status_label ?? po.status}
                      </span>
                    </td>
                    <td>{po.status_reason ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">Purchase orders will appear here once procurement begins.</div>
          )}
        </div>
      </div>

      {purchaseSummary.rejected ? (
        <Alert variant="warning">
          {purchaseSummary.rejected} purchase order{purchaseSummary.rejected === 1 ? '' : 's'} ha{purchaseSummary.rejected === 1 ? 's' : 've'} been rejected at receipt because the warehouse would have exceeded capacity.
        </Alert>
      ) : null}
    </div>
  );
};

export default Suppliers;
