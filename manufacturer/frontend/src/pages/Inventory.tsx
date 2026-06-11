import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Table } from 'react-bootstrap';
import { FaBoxes, FaWarehouse } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import ResponsivePlot from '../components/ResponsivePlot';
import { getErrorMessage, inventoryAPI, materialsAPI } from '../services/api';
import type { CapacityInfo, InventoryLevel, Product } from '../types';
import { announceSimulationUpdate, onSimulationUpdate } from '../utils/simulationEvents';
import { formatNumber, formatTimestamp } from '../utils/formatters';
import LoadingSpinner from '../components/LoadingSpinner';

const Inventory: React.FC = () => {
  const [inventory, setInventory] = useState<InventoryLevel[]>([]);
  const [capacity, setCapacity] = useState<CapacityInfo | null>(null);
  const [materials, setMaterials] = useState<Product[]>([]);
  const [adjustmentLogs, setAdjustmentLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adjustProductId, setAdjustProductId] = useState('');
  const [adjustQuantity, setAdjustQuantity] = useState('');
  const [adjustReason, setAdjustReason] = useState('');

  const loadInventory = async () => {
    try {
      setLoading(true);
      const [inventoryRes, capacityRes, materialsRes, logsRes] = await Promise.all([
        inventoryAPI.getInventory(),
        inventoryAPI.getCapacity(),
        materialsAPI.getMaterials(),
        inventoryAPI.getAdjustmentLogs(),
      ]);
      setInventory(inventoryRes.data);
      setCapacity(capacityRes.data);
      setMaterials(materialsRes.data);
      setAdjustmentLogs(logsRes.data);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load inventory and warehouse data.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadInventory();
    const clear = onSimulationUpdate(() => {
      void loadInventory();
    });

    return clear;
  }, []);

  const materialMap = useMemo(() => new Map(materials.map((material) => [material.id, material.name])), [materials]);

  const handleManualAdjust = async () => {
    const quantity = Number(adjustQuantity);
    if (!adjustProductId || Number.isNaN(quantity) || quantity === 0) {
      return;
    }

    try {
      await inventoryAPI.manualAdjust({ product_id: adjustProductId, quantity, reason: adjustReason || undefined });
      setAdjustProductId('');
      setAdjustQuantity('');
      setAdjustReason('');
      setMessage(`Inventory adjusted by ${quantity > 0 ? '+' : ''}${quantity}.`);
      announceSimulationUpdate();
      await loadInventory();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to adjust inventory.'));
    }
  };

  const stockChart = inventory
    .map((item) => ({
      name: item.product_name ?? materialMap.get(item.product_id) ?? item.product_id,
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
          <h1>Warehouse flow and storage pressure</h1>
          <p>See what procurement receipts add, what manufacturing consumes, and how much warehouse space is still available before incoming deliveries get rejected.</p>
        </div>
      </div>

      <PageGuide
        title="Inventory"
        controls="This screen shows the current raw-material stock and lets you make manual adjustments when you want to simulate audits, scrap, emergency receipts, or corrected counts."
        next="Inventory levels directly affect whether manufacturing orders can be released and whether future purchase orders can be received without exceeding warehouse capacity."
        tip="A supplier is not rejecting a purchase order. If a PO ends up rejected, the warehouse could not receive it because total stored units would have exceeded the configured capacity on delivery. Ordered not yet delivered shows inbound stock that is already on open purchase orders but has not arrived yet."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      {capacity ? (
        <div className="kpi-grid">
          <div className="kpi-card info">
            <div className="kpi-label">Warehouse Capacity</div>
            <div className="kpi-value"><FaWarehouse /></div>
            <div className="kpi-subtext">{formatNumber(capacity.warehouse_capacity)} total units</div>
          </div>
          <div className="kpi-card warning">
            <div className="kpi-label">Stored Now</div>
            <div className="kpi-value">{formatNumber(capacity.current_usage)}</div>
            <div className="kpi-subtext">Units currently occupying space</div>
          </div>
          <div className="kpi-card success">
            <div className="kpi-label">Free Space</div>
            <div className="kpi-value">{formatNumber(capacity.available_capacity)}</div>
            <div className="kpi-subtext">Units still available for receipts</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Utilization</div>
            <div className="kpi-value">{capacity.usage_percentage.toFixed(1)}%</div>
            <div className="kpi-subtext">Storage pressure right now</div>
          </div>
        </div>
      ) : null}

      <div className="two-column">
        <div className="chart-container">
          <ResponsivePlot
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
              title: { text: 'Raw material stock levels' },
              xaxis: { title: { text: 'Units on hand' } },
              margin: { t: 68, r: 24, b: 56, l: 160 },
            }}
            minHeight={380}
          />
        </div>

        <Card>
          <Card.Header><FaBoxes className="me-2" />Manual inventory adjustment</Card.Header>
          <Card.Body>
            <p className="text-muted">
              Use this only when you want to simulate a manual correction. Positive values add stock to the warehouse. Negative values remove stock from the warehouse.
            </p>
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
              <Form.Text>Example: <span className="mono">+100</span> for an emergency receipt or <span className="mono">-25</span> for scrap and shrinkage.</Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Reason (optional)</Form.Label>
              <Form.Control
                type="text"
                value={adjustReason}
                onChange={(event) => setAdjustReason(event.target.value)}
                placeholder="e.g., Inventory audit, Emergency supply, Shrinkage correction"
              />
            </Form.Group>
            <Button variant="primary" onClick={handleManualAdjust} disabled={!adjustProductId || !adjustQuantity}>
              Apply inventory adjustment
            </Button>
          </Card.Body>
        </Card>
      </div>

      <div className="card">
        <div className="card-header">Current raw-material inventory</div>
        <div className="card-body p-0">
          {inventory.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Material</th>
                  <th>Stock</th>
                  <th>Needed for accepted orders</th>
                  <th>Ordered not yet delivered</th>
                  <th>Storage Status</th>
                  <th>Last Updated</th>
                </tr>
              </thead>
              <tbody>
                {inventory.map((item) => {
                  const stockState = getStockState(item.quantity);
                  return (
                    <tr key={item.product_id}>
                      <td><strong>{item.product_name ?? materialMap.get(item.product_id) ?? item.product_id}</strong></td>
                      <td>{formatNumber(item.quantity, 2)}</td>
                      <td>{formatNumber(item.accepted_order_demand, 2)}</td>
                      <td>{formatNumber(item.pending_inbound_quantity, 2)}</td>
                      <td><span className={`badge ${stockState.className}`}>{stockState.label}</span></td>
                      <td>{formatTimestamp(item.last_updated)}</td>
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

      <div className="card">
        <div className="card-header">Material adjustments &amp; trash log</div>
        <div className="card-body p-0">
          {adjustmentLogs.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Material</th>
                  <th>Type</th>
                  <th>Quantity</th>
                  <th>Reason</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {adjustmentLogs.map((log) => (
                  <tr key={log.id}>
                    <td>{log.sim_date}</td>
                    <td><strong>{log.product_name || log.product_id}</strong></td>
                    <td>
                      <span className={`badge ${log.adjustment_type === 'TRASHED' ? 'badge-danger' : 'badge-info'}`}>
                        {log.adjustment_type === 'TRASHED' ? '🗑️ Trashed' : '✏️ Adjusted'}
                      </span>
                    </td>
                    <td>{log.quantity > 0 ? '+' : ''}{formatNumber(log.quantity, 2)}</td>
                    <td>{log.reason}</td>
                    <td>{formatTimestamp(log.timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">No material adjustments or trash events yet.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Inventory;
