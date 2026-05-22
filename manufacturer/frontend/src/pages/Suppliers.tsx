import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Modal, Table, Collapse } from 'react-bootstrap';
import { FaPlus, FaShoppingCart, FaTrash, FaCheckCircle, FaTimesCircle, FaLink } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import { getErrorMessage, materialsAPI, purchaseOrdersAPI, suppliersAPI, providersAPI } from '../services/api';
import type { Product, PurchaseOrder, Supplier, ProviderCatalog, ProviderInfo, ProviderProduct } from '../types';
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
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [providerCatalogs, setProviderCatalogs] = useState<Map<string, ProviderCatalog>>(new Map());
  const [loading, setLoading] = useState(true);
  const [savingSupplier, setSavingSupplier] = useState(false);
  const [savingPo, setSavingPo] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAddLocal, setShowAddLocal] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [showProviderSettings, setShowProviderSettings] = useState(false);
  const [selectedProviderProduct, setSelectedProviderProduct] = useState<{provider: string; product: ProviderProduct} | null>(null);
  const [linkingMaterial, setLinkingMaterial] = useState('');
  const [savingLink, setSavingLink] = useState(false);
  const [providerUrlEdits, setProviderUrlEdits] = useState<Record<string, string>>({});
  const [savingProviderUrls, setSavingProviderUrls] = useState(false);

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
      const [suppliersRes, materialsRes, poRes, providersRes] = await Promise.all([
        suppliersAPI.getSuppliers(),
        materialsAPI.getMaterials(),
        purchaseOrdersAPI.getPurchaseOrders(),
        providersAPI.getProviders(),
      ]);
      setSuppliers(suppliersRes.data);
      setMaterials(materialsRes.data);
      setPurchaseOrders(poRes.data);
      setProviders(providersRes.data);
      setError(null);

      const catalogMap = new Map<string, ProviderCatalog>();
      for (const provider of providersRes.data) {
        if (provider.online) {
          try {
            const catalogRes = await providersAPI.getProviderCatalog(provider.name);
            catalogMap.set(provider.name, catalogRes.data);
          } catch {
            catalogMap.set(provider.name, { name: provider.name, url: provider.url, online: false });
          }
        } else {
          catalogMap.set(provider.name, { name: provider.name, url: provider.url, online: false });
        }
      }
      setProviderCatalogs(catalogMap);
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

  const linkedProviderProducts = useMemo(() => {
    const linked = new Map<string, Set<number>>();
    for (const supplier of suppliers) {
      if (supplier.external_provider_url && supplier.external_product_id) {
        if (!linked.has(supplier.external_provider_url)) {
          linked.set(supplier.external_provider_url, new Set());
        }
        linked.get(supplier.external_provider_url)!.add(supplier.external_product_id);
      }
    }
    return linked;
  }, [suppliers]);

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
      setMessage('Local supplier created successfully.');
      setShowAddLocal(false);
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

  const linkProviderProduct = async () => {
    if (!selectedProviderProduct || !linkingMaterial) {
      return;
    }

    try {
      setSavingLink(true);
      const product = selectedProviderProduct.product;
      const providerUrl = providers.find(p => p.name === selectedProviderProduct.provider)?.url;
      if (!providerUrl) {
        throw new Error('Provider URL not found');
      }

      await suppliersAPI.createSupplier({
        name: selectedProviderProduct.provider,
        product_id: linkingMaterial,
        unit_cost: Number(product.pricing_tiers?.[0]?.unit_price ?? 0),
        lead_time_days: product.lead_time_days,
        quantity_breaks: product.pricing_tiers?.map((tier) => ({
          qty: tier.min_quantity,
          price: Number(tier.unit_price),
        })) ?? [],
        external_provider_url: providerUrl,
        external_product_id: product.id,
      });
      setMessage(`Linked ${product.name} as external supplier from ${selectedProviderProduct.provider}.`);
      setShowLinkModal(false);
      setSelectedProviderProduct(null);
      setLinkingMaterial('');
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to link provider product.'));
    } finally {
      setSavingLink(false);
    }
  };

  const saveProviderUrls = async () => {
    try {
      setSavingProviderUrls(true);
      for (const [providerName, url] of Object.entries(providerUrlEdits)) {
        await providersAPI.updateProviderUrl(providerName, url);
      }
      setMessage('Provider URLs updated successfully.');
      setProviderUrlEdits({});
      setShowProviderSettings(false);
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to update provider URLs.'));
    } finally {
      setSavingProviderUrls(false);
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
      setPoForm({ supplier_id: '', quantity: '100' });
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
          <p>Source materials from external providers or manage local suppliers. Create purchase orders and track inventory replenishment across the supply chain.</p>
        </div>
      </div>

      <PageGuide
        title="Procurement"
        controls="Link products from online providers or create local suppliers. Supplier pricing can change with quantity breaks, and every purchase order enters transit with the chosen lead time."
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

      {/* Provider Settings */}
      {providers.length > 0 && (
        <div>
          <Button
            variant="outline-secondary"
            onClick={() => setShowProviderSettings(!showProviderSettings)}
            aria-expanded={showProviderSettings}
            className="mb-3 mt-4"
          >
            {showProviderSettings ? '▼' : '▶'} Configure Provider URLs
          </Button>
          <Collapse in={showProviderSettings}>
            <Card className="mb-4">
              <Card.Body>
                <p className="text-muted mb-4">
                  If providers are unreachable at their configured URLs (e.g., running on different hosts), you can override them here.
                  Leave blank to use the default URL from config.json.
                </p>
                {providers.map((provider) => (
                  <Form.Group key={provider.name} className="mb-3">
                    <Form.Label><strong>{provider.name}</strong></Form.Label>
                    <Form.Control
                      type="text"
                      value={providerUrlEdits[provider.name] ?? provider.url}
                      onChange={(e) => setProviderUrlEdits({ ...providerUrlEdits, [provider.name]: e.target.value })}
                      placeholder={`Default: ${provider.url}`}
                    />
                    <Form.Text className="text-muted">
                      Current: {provider.url}
                    </Form.Text>
                  </Form.Group>
                ))}
                <Button
                  variant="primary"
                  onClick={saveProviderUrls}
                  disabled={savingProviderUrls || Object.keys(providerUrlEdits).length === 0}
                  className="me-2"
                >
                  {savingProviderUrls ? 'Saving...' : 'Save Provider URLs'}
                </Button>
                <Button
                  variant="outline-secondary"
                  onClick={() => {
                    setProviderUrlEdits({});
                    setShowProviderSettings(false);
                  }}
                >
                  Cancel
                </Button>
              </Card.Body>
            </Card>
          </Collapse>
        </div>
      )}

      {/* Section 1: Provider Services */}
      {providers.length > 0 && (
        <div>
          <h2 className="mt-5 mb-3">Provider Services</h2>
          <p className="text-muted mb-4">
            <strong>Monitor and manage your suppliers.</strong> This section shows all available products from external providers.
            Products with a checkmark are already linked as suppliers. Click "Link as Supplier" to add alternative sources for materials.
          </p>
          {providers.map((provider) => {
            const catalog = providerCatalogs.get(provider.name);
            return (
              <Card key={provider.name} className="mb-4">
                <Card.Header className="d-flex justify-content-between align-items-center">
                  <div>
                    <strong>{provider.name}</strong>
                    {' '}
                    <code className="text-muted">{provider.url}</code>
                  </div>
                  {provider.online ? (
                    <span className="badge bg-success"><FaCheckCircle className="me-1" />Online</span>
                  ) : (
                    <span className="badge bg-danger"><FaTimesCircle className="me-1" />Offline</span>
                  )}
                </Card.Header>
                <Card.Body>
                  {provider.online && catalog?.products && catalog.products.length > 0 ? (
                    <Table responsive hover>
                      <thead>
                        <tr>
                          <th>Product</th>
                          <th>Stock</th>
                          <th>Lead Time</th>
                          <th>Base Price</th>
                          <th>Pricing Tiers</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {catalog.products.map((product) => {
                          const linkedProductIds = linkedProviderProducts.get(provider.url);
                          const isLinked = linkedProductIds?.has(product.id) ?? false;
                          return (
                            <tr key={product.id}>
                              <td><strong>{product.name}</strong></td>
                              <td>{product.stock_quantity} units</td>
                              <td>{product.lead_time_days} days</td>
                              <td>{formatCurrency(Number(product.pricing_tiers?.[0]?.unit_price ?? 0))}</td>
                              <td>
                                {product.pricing_tiers && product.pricing_tiers.length > 1 ? (
                                  product.pricing_tiers.map((tier) => (
                                    <span key={`${tier.min_quantity}`} className="badge badge-neutral me-2">
                                      {tier.min_quantity}+ @ {formatCurrency(Number(tier.unit_price))}
                                    </span>
                                  ))
                                ) : (
                                  <span className="text-muted">No tiers</span>
                                )}
                              </td>
                              <td>
                                <Button
                                  variant={isLinked ? 'secondary' : 'outline-primary'}
                                  size="sm"
                                  onClick={() => {
                                    if (!isLinked) {
                                      setSelectedProviderProduct({ provider: provider.name, product });
                                      setShowLinkModal(true);
                                    }
                                  }}
                                  disabled={isLinked}
                                >
                                  {isLinked ? '✓ Linked' : 'Link as Supplier'}
                                </Button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </Table>
                  ) : !provider.online ? (
                    <Alert variant="warning" className="mb-0">
                      <strong>{provider.name}</strong> is currently offline. Catalog data is unavailable. Existing suppliers from this provider will continue to function based on cached settings.
                    </Alert>
                  ) : (
                    <div className="text-muted">No products available from this provider.</div>
                  )}
                </Card.Body>
              </Card>
            );
          })}
        </div>
      )}

      {/* Section 2: Your Suppliers */}
      <h2 className="mt-5 mb-3">Your Suppliers</h2>
      <p className="text-muted mb-3">
        <strong>Your active supplier network.</strong> These are the suppliers you can order from.
        <span className="badge badge-info ms-2">External</span> suppliers pull live pricing from providers.
        <span className="badge badge-secondary ms-2">Local</span> suppliers are configured manually.
        Use "Order" to create a purchase order.
      </p>
      <div className="card mb-4">
        <div className="card-body p-0">
          {suppliers.length ? (
            <Table responsive hover className="mb-0">
              <thead>
                <tr>
                  <th>Material</th>
                  <th>Supplier Name</th>
                  <th>Type</th>
                  <th>Lead Time</th>
                  <th>Base Price</th>
                  <th>Pricing Tiers</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((supplier) => (
                  <tr key={supplier.id}>
                    <td><strong>{supplier.product_name ?? materialMap.get(supplier.product_id) ?? supplier.product_id}</strong></td>
                    <td>{supplier.name}</td>
                    <td>
                      {supplier.external_provider_url ? (
                        <span className="badge badge-info">External</span>
                      ) : (
                        <span className="badge badge-secondary">Local</span>
                      )}
                    </td>
                    <td>{supplier.lead_time_days} days</td>
                    <td>{formatCurrency(Number(supplier.unit_cost))}</td>
                    <td>
                      {supplier.quantity_breaks?.length ? supplier.quantity_breaks.map((tier) => (
                        <span key={`${tier.qty}-${tier.price}`} className="badge badge-neutral me-2">
                          {tier.qty}+ @ {formatCurrency(Number(tier.price))}
                        </span>
                      )) : <span className="text-muted">No tiers</span>}
                    </td>
                    <td>
                      <Button
                        variant="outline-primary"
                        size="sm"
                        className="me-2"
                        onClick={() => {
                          setPoForm({ supplier_id: supplier.id, quantity: '100' });
                          document.getElementById('purchase-order-section')?.scrollIntoView({ behavior: 'smooth' });
                        }}
                      >
                        Order
                      </Button>
                      <Button variant="outline-danger" size="sm" onClick={() => void deleteSupplier(supplier.id)}>
                        <FaTrash />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state p-4">Link external suppliers or create local ones to start replenishing materials.</div>
          )}
        </div>
      </div>

      {/* Section 3: Create Purchase Order */}
      <h2 id="purchase-order-section" className="mt-5 mb-3">Create Purchase Order</h2>
      <p className="text-muted mb-3">
        <strong>Order materials to replenish inventory.</strong> Select a supplier and quantity.
        Pricing automatically applies quantity breaks. Orders enter transit with the supplier's lead time
        and arrive as long as warehouse capacity allows.
      </p>
      <Card className="mb-4">
        <Card.Header><FaShoppingCart className="me-2" />New Purchase Order</Card.Header>
        <Card.Body>
          <Form.Group className="mb-3">
            <Form.Label>Supplier</Form.Label>
            <Form.Select value={poForm.supplier_id} onChange={(event) => setPoForm({ ...poForm, supplier_id: event.target.value })}>
              <option value="">Select a supplier</option>
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
                Tier pricing updates live as quantity changes.
              </div>
            </div>
          ) : null}
          <Button variant="success" onClick={createPurchaseOrder} disabled={savingPo || !selectedSupplier || selectedQuantity <= 0}>
            {savingPo ? 'Creating PO...' : 'Create purchase order'}
          </Button>
        </Card.Body>
      </Card>

      {/* Section 4: Add Local Supplier (Collapsible) */}
      <h2 className="mt-5 mb-3">Add Local Supplier</h2>
      <p className="text-muted mb-3">
        <strong>Manually configure suppliers.</strong> Use this to add local suppliers not from external providers,
        or to create alternative sources for materials. Set your own pricing, lead times, and quantity breaks.
      </p>
      <Button
        variant="outline-secondary"
        onClick={() => setShowAddLocal(!showAddLocal)}
        aria-expanded={showAddLocal}
        className="mb-3"
      >
        {showAddLocal ? '▼' : '▶'} {showAddLocal ? 'Hide' : 'Show'} local supplier form
      </Button>
      <Collapse in={showAddLocal}>
        <Card className="mb-4">
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
              {savingSupplier ? 'Creating supplier...' : 'Create local supplier'}
            </Button>
          </Card.Body>
        </Card>
      </Collapse>

      {/* Purchase Order Log */}
      <h2 className="mt-5 mb-3">Purchase-Order Log</h2>
      <p className="text-muted mb-3">
        <strong>Track all material orders.</strong> Shows every purchase order with its status.
        Orders start as "In Transit" and become "Received" when they arrive.
        "Rejected" means the warehouse couldn't receive them due to capacity limits.
      </p>
      <div className="card">
        <div className="card-body p-0">
          {purchaseOrders.length ? (
            <Table responsive hover className="mb-0">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Supplier</th>
                  <th>Material</th>
                  <th>Quantity</th>
                  <th>Unit Cost</th>
                  <th>Total Cost</th>
                  <th>Expected Delivery</th>
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
            <div className="empty-state p-4">Purchase orders will appear here once procurement begins.</div>
          )}
        </div>
      </div>

      {purchaseSummary.rejected ? (
        <Alert variant="warning" className="mt-4">
          {purchaseSummary.rejected} purchase order{purchaseSummary.rejected === 1 ? '' : 's'} ha{purchaseSummary.rejected === 1 ? 's' : 've'} been rejected at receipt because the warehouse would have exceeded capacity.
        </Alert>
      ) : null}

      {/* Link Provider Product Modal */}
      <Modal show={showLinkModal} onHide={() => { setShowLinkModal(false); setSelectedProviderProduct(null); setLinkingMaterial(''); }}>
        <Modal.Header closeButton>
          <Modal.Title>Link as Supplier</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {selectedProviderProduct && (
            <>
              <div className="mb-3">
                <strong>Provider:</strong> {selectedProviderProduct.provider}
              </div>
              <div className="mb-3">
                <strong>Product:</strong> {selectedProviderProduct.product.name}
              </div>
              <Form.Group className="mb-3">
                <Form.Label>Link to material</Form.Label>
                <Form.Select value={linkingMaterial} onChange={(e) => setLinkingMaterial(e.target.value)}>
                  <option value="">Select a material</option>
                  {materials.map((material) => (
                    <option key={material.id} value={material.id}>{material.name}</option>
                  ))}
                </Form.Select>
              </Form.Group>
              <div className="mb-3">
                <strong>Lead time:</strong> {selectedProviderProduct.product.lead_time_days} days
              </div>
              <div className="mb-3">
                <strong>Base price:</strong> {formatCurrency(Number(selectedProviderProduct.product.pricing_tiers?.[0]?.unit_price ?? 0))}
              </div>
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => { setShowLinkModal(false); setSelectedProviderProduct(null); setLinkingMaterial(''); }}>
            Cancel
          </Button>
          <Button variant="primary" onClick={linkProviderProduct} disabled={savingLink || !linkingMaterial}>
            {savingLink ? 'Linking...' : 'Confirm Link'}
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
};

export default Suppliers;
