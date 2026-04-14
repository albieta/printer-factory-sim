import React, { useEffect, useMemo, useState } from 'react';
import Plot from 'react-plotly.js';
import { Alert, Button, Card, Form, Table } from 'react-bootstrap';
import { FaBoxes, FaWarehouse } from 'react-icons/fa';
import { getErrorMessage, inventoryAPI, materialsAPI } from '../services/api';
import type { CapacityInfo, InventoryLevel, Product } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Inventory: React.FC = () => {
  const [inventory, setInventory] = useState<InventoryLevel[]>([]);
  const [capacity, setCapacity] = useState<CapacityInfo | null>(null);
  const [materials, setMaterials] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adjustProductId, setAdjustProductId] = useState('');
  const [adjustQuantity, setAdjustQuantity] = useState('');

  const loadInventory = async () => {
    try {
      setLoading(true);
      const [inventoryRes, capacityRes, materialsRes] = await Promise.all([
        inventoryAPI.getInventory(),
        inventoryAPI.getCapacity(),
        materialsAPI.getMaterials(),
      ]);
      setInventory(inventoryRes.data);
      setCapacity(capacityRes.data);
      setMaterials(materialsRes.data);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load inventory and warehouse data.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadInventory();
  }, []);

  const materialMap = useMemo(() => new Map(materials.map((material) => [material.id, material.name])), [materials]);

  const handleManualAdjust = async () => {
    const quantity = Number(adjustQuantity);
    if (!adjustProductId || Number.isNaN(quantity) || quantity === 0) {
      return;
    }

    try {
      await inventoryAPI.manualAdjust({ product_id: adjustProductId, quantity });
      setAdjustProductId('');
      setAdjustQuantity('');
      await loadInventory();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to adjust inventory.'));
    }
  };

  const stockChart = inventory
    .map((item) => ({
      name: materialMap.get(item.product_id) ?? item.product_id.slice(0, 8),
      quantity: item.quantity,
    }))
    .sort((a, b) => b.quantity - a.quantity);

  const getStockState = (quantity: number) => {
    if (quantity >= 150) {
      return { label: 'Healthy', className: 'badge-completed' };
    }
    if (quantity >= 60) {
      return { label: 'Watch', className: 'badge-pending' };
    }
    return { label: 'Critical', className: 'badge-blocked' };
  };

  if (loading) {
    return <LoadingSpinner label="Loading warehouse inventory..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Inventory</div>
          <h1>Warehouse control</h1>
          <p>Monitor raw material levels, adjust stock manually, and keep storage utilization inside the configured limits.</p>
        </div>
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {capacity ? (
        <div className="kpi-grid">
          <div className="kpi-card info">
            <div className="kpi-label">Warehouse Capacity</div>
            <div className="kpi-value"><FaWarehouse /></div>
            <div className="kpi-subtext">{capacity.warehouse_capacity.toLocaleString()} total units</div>
          </div>
          <div className="kpi-card warning">
            <div className="kpi-label">Current Usage</div>
            <div className="kpi-value">{capacity.current_usage.toFixed(0)}</div>
            <div className="kpi-subtext">Units currently stored</div>
          </div>
          <div className="kpi-card success">
            <div className="kpi-label">Available Space</div>
            <div className="kpi-value">{capacity.available_capacity.toFixed(0)}</div>
            <div className="kpi-subtext">Units still available</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Utilization</div>
            <div className="kpi-value">{capacity.usage_percentage.toFixed(1)}%</div>
            <div className="kpi-subtext">Warehouse saturation rate</div>
          </div>
        </div>
      ) : null}

      <div className="two-column">
        <div className="chart-container">
          <div className="section-title">
            <h4>Material stock levels</h4>
          </div>
          {stockChart.length ? (
            <Plot
              data={[
                {
                  x: stockChart.map((item) => item.quantity),
                  y: stockChart.map((item) => item.name),
                  type: 'bar',
                  orientation: 'h',
                  marker: { color: '#1a6b67' },
                },
              ]}
              layout={{
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                margin: { t: 12, r: 12, b: 36, l: 120 },
                xaxis: { title: { text: 'Units on hand' } },
              }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: '360px' }}
            />
          ) : (
            <div className="empty-state">No inventory records are available yet.</div>
          )}
        </div>

        <Card>
          <Card.Header><FaBoxes className="me-2" />Manual adjustment</Card.Header>
          <Card.Body>
            <Form.Group className="mb-3">
              <Form.Label>Material</Form.Label>
              <Form.Select value={adjustProductId} onChange={(event) => setAdjustProductId(event.target.value)}>
                <option value="">Select a material</option>
                {materials.map((material) => (
                  <option key={material.id} value={material.id}>{material.name}</option>
                ))}
              </Form.Select>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Quantity delta</Form.Label>
              <Form.Control
                type="number"
                value={adjustQuantity}
                onChange={(event) => setAdjustQuantity(event.target.value)}
                placeholder="Use a positive or negative number"
              />
              <Form.Text>Positive values add stock. Negative values remove stock.</Form.Text>
            </Form.Group>
            <Button variant="primary" onClick={handleManualAdjust} disabled={!adjustProductId || !adjustQuantity}>
              Apply inventory adjustment
            </Button>
          </Card.Body>
        </Card>
      </div>

      <div className="card">
        <div className="card-header">Current raw material inventory</div>
        <div className="card-body p-0">
          {inventory.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Material</th>
                  <th>Product ID</th>
                  <th>Stock</th>
                  <th>Last Updated</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {inventory.map((item) => {
                  const stockState = getStockState(item.quantity);
                  return (
                    <tr key={item.product_id}>
                      <td><strong>{materialMap.get(item.product_id) ?? item.product_id.slice(0, 8)}</strong></td>
                      <td><span className="mono">{item.product_id}</span></td>
                      <td>{item.quantity.toFixed(2)}</td>
                      <td>{new Date(item.last_updated).toLocaleString()}</td>
                      <td><span className={`badge ${stockState.className}`}>{stockState.label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">Inventory will appear here once stock is seeded or purchase orders are delivered.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Inventory;
