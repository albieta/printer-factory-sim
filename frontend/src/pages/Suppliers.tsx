import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Table } from 'react-bootstrap';
import { FaPlus, FaShoppingCart, FaTrash } from 'react-icons/fa';
import { getErrorMessage, materialsAPI, purchaseOrdersAPI, suppliersAPI } from '../services/api';
import type { Product, PurchaseOrder, Supplier } from '../types';
import { PurchaseOrderStatus } from '../types';
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
    .filter((entry) => !Number.isNaN(entry.qty) && !Number.isNaN(entry.price));
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
  }, []);

  const materialMap = useMemo(() => new Map(materials.map((material) => [material.id, material.name])), [materials]);
  const supplierMap = useMemo(() => new Map(suppliers.map((supplier) => [supplier.id, supplier.name])), [suppliers]);
  const selectedSupplier = suppliers.find((supplier) => supplier.id === poForm.supplier_id) ?? null;

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
        quantity: Number(poForm.quantity),
      });
      setMessage('Purchase order created successfully.');
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
    const spend = purchaseOrders.reduce((total, order) => total + order.quantity * order.unit_cost, 0);
    return { pending, delivered, spend };
  }, [purchaseOrders]);

  if (loading) {
    return <LoadingSpinner label="Loading suppliers and purchasing..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Suppliers</div>
          <h1>Procurement desk</h1>
          <p>Set up vendors, define tiered pricing, and create purchase orders that replenish the materials your line depends on.</p>
        </div>
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      <div className="kpi-grid">
        <div className="kpi-card info">
          <div className="kpi-label">Suppliers</div>
          <div className="kpi-value">{suppliers.length}</div>
          <div className="kpi-subtext">Active vendors in the network</div>
        </div>
        <div className="kpi-card warning">
          <div className="kpi-label">Pending POs</div>
          <div className="kpi-value">{purchaseSummary.pending}</div>
          <div className="kpi-subtext">Open replenishment orders in transit</div>
        </div>
        <div className="kpi-card success">
          <div className="kpi-label">Delivered POs</div>
          <div className="kpi-value">{purchaseSummary.delivered}</div>
          <div className="kpi-subtext">Delivered successfully into inventory</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Committed Spend</div>
          <div className="kpi-value">${purchaseSummary.spend.toFixed(0)}</div>
          <div className="kpi-subtext">Total value of recorded purchase orders</div>
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
            <div className="two-column">
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
                placeholder="100:9.5, 500:8.75"
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
                    {supplier.name} - {materialMap.get(supplier.product_id) ?? supplier.product_id.slice(0, 8)}
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
                  <strong>{materialMap.get(selectedSupplier.product_id) ?? selectedSupplier.product_id.slice(0, 8)}</strong>
                </div>
                <div className="stat-row mt-2">
                  <span>Lead time</span>
                  <strong>{selectedSupplier.lead_time_days} days</strong>
                </div>
                <div className="stat-row mt-2">
                  <span>Base cost</span>
                  <strong>${Number(selectedSupplier.unit_cost).toFixed(2)}</strong>
                </div>
              </div>
            ) : null}
            <Button variant="success" onClick={createPurchaseOrder} disabled={savingPo || !selectedSupplier || Number(poForm.quantity) <= 0}>
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
                  <th>Unit Cost</th>
                  <th>Lead Time</th>
                  <th>Pricing Tiers</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((supplier) => (
                  <tr key={supplier.id}>
                    <td><strong>{supplier.name}</strong></td>
                    <td>{materialMap.get(supplier.product_id) ?? supplier.product_id}</td>
                    <td>${Number(supplier.unit_cost).toFixed(2)}</td>
                    <td>{supplier.lead_time_days} days</td>
                    <td>
                      {supplier.quantity_breaks?.length ? supplier.quantity_breaks.map((tier) => (
                        <span key={`${tier.qty}-${tier.price}`} className="badge badge-neutral me-2">
                          {tier.qty}+ @ ${Number(tier.price).toFixed(2)}
                        </span>
                      )) : <span className="text-muted">No tier pricing</span>}
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
        <div className="card-header">Purchase order log</div>
        <div className="card-body p-0">
          {purchaseOrders.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>PO</th>
                  <th>Supplier</th>
                  <th>Material</th>
                  <th>Quantity</th>
                  <th>Unit Cost</th>
                  <th>Issued</th>
                  <th>Expected Delivery</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {purchaseOrders.map((po) => (
                  <tr key={po.id}>
                    <td><span className="mono">{po.id.slice(0, 8)}</span></td>
                    <td>{supplierMap.get(po.supplier_id) ?? po.supplier_id}</td>
                    <td>{materialMap.get(po.product_id) ?? po.product_id}</td>
                    <td>{po.quantity}</td>
                    <td>${Number(po.unit_cost).toFixed(2)}</td>
                    <td>{po.issue_date}</td>
                    <td>{po.expected_delivery}</td>
                    <td>
                      <span className={`badge ${po.status === PurchaseOrderStatus.DELIVERED ? 'badge-completed' : po.status === PurchaseOrderStatus.REJECTED ? 'badge-blocked' : 'badge-pending'}`}>
                        {po.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">Purchase orders will appear here once procurement begins.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Suppliers;
