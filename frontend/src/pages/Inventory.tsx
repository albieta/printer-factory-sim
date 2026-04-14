import React, { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';
import { Row, Col, Card, Table, Form, Button, Alert } from 'react-bootstrap';
import { FaBoxes, FaWarehouse } from 'react-icons/fa';
import { inventoryAPI, materialsAPI } from '../services/api';
import type { InventoryLevel, CapacityInfo, Product } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Inventory: React.FC = () => {
  const [inventory, setInventory] = useState<InventoryLevel[]>([]);
  const [capacity, setCapacity] = useState<CapacityInfo | null>(null);
  const [materials, setMaterials] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adjustProductId, setAdjustProductId] = useState<string>('');
  const [adjustQuantity, setAdjustQuantity] = useState<number>(0);

  const fetchData = async () => {
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
    } catch (err: any) {
      setError('Failed to load inventory data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleManualAdjust = async () => {
    if (!adjustProductId || adjustQuantity === 0) return;
    
    try {
      await inventoryAPI.manualAdjust({
        product_id: adjustProductId,
        quantity: adjustQuantity,
      });
      setAdjustProductId('');
      setAdjustQuantity(0);
      await fetchData();
    } catch (err: any) {
      setError('Failed to adjust inventory');
    }
  };

  const getMaterialName = (productId: string) => {
    const material = materials.find(m => m.id === productId);
    return material?.name || productId.substring(0, 12);
  };

  if (loading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1>Inventory Management</h1>
        <p>Track raw material stock levels and warehouse capacity</p>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {/* Capacity Overview */}
      {capacity && (
        <Row className="mb-4">
          <Col md={4}>
            <div className="kpi-card">
              <div className="kpi-label">Warehouse Capacity</div>
              <div className="kpi-value"><FaWarehouse /></div>
              <div className="kpi-subtext">{capacity.warehouse_capacity.toLocaleString()} units</div>
            </div>
          </Col>
          <Col md={4}>
            <div className="kpi-card warning">
              <div className="kpi-label">Current Usage</div>
              <div className="kpi-value">{capacity.current_usage.toLocaleString()}</div>
              <div className="kpi-subtext">units in stock</div>
            </div>
          </Col>
          <Col md={4}>
            <div className="kpi-card success">
              <div className="kpi-label">Available Capacity</div>
              <div className="kpi-value">{capacity.available_capacity.toLocaleString()}</div>
              <div className="kpi-subtext">{capacity.usage_percentage.toFixed(1)}% utilized</div>
            </div>
          </Col>
        </Row>
      )}

      {/* Capacity Gauge */}
      {capacity && (
        <div className="chart-container mb-4">
          <h4 style={{ marginBottom: '20px', fontWeight: 600 }}>Warehouse Capacity Utilization</h4>
          <Plot
            data={[
              {
                type: 'indicator',
                mode: 'gauge+number',
                value: capacity.usage_percentage,
                gauge: {
                  axis: { range: [0, 100] },
                  bar: { color: '#1976d2' },
                  steps: [
                    { range: [0, 50], color: '#4caf50' },
                    { range: [50, 80], color: '#ff9800' },
                    { range: [80, 100], color: '#f44336' },
                  ],
                },
              }
            ]}
            layout={{ 
              margin: { t: 40, b: 20, l: 40, r: 40 },
              height: 250
            }}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      )}

      {/* Manual Adjustment */}
      <Card className="mb-4">
        <Card.Header>
          <strong><FaBoxes /> Manual Inventory Adjustment</strong>
        </Card.Header>
        <Card.Body>
          <Row>
            <Col md={4}>
              <Form.Group>
                <Form.Label>Material</Form.Label>
                <Form.Select 
                  value={adjustProductId}
                  onChange={(e) => setAdjustProductId(e.target.value)}
                >
                  <option value="">Select material...</option>
                  {materials.map(m => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col md={4}>
              <Form.Group>
                <Form.Label>Quantity (positive to add, negative to remove)</Form.Label>
                <Form.Control
                  type="number"
                  value={adjustQuantity}
                  onChange={(e) => setAdjustQuantity(parseInt(e.target.value))}
                  placeholder="Enter quantity..."
                />
              </Form.Group>
            </Col>
            <Col md={4} className="d-flex align-items-end">
              <Button 
                variant="primary" 
                onClick={handleManualAdjust}
                disabled={!adjustProductId || adjustQuantity === 0}
              >
                Adjust Inventory
              </Button>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {/* Stock Levels Table */}
      <div className="card">
        <div className="card-header">Stock Levels</div>
        <div className="card-body p-0">
          {inventory.length > 0 ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Material</th>
                  <th>Product ID</th>
                  <th>Current Stock</th>
                  <th>Last Updated</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {inventory.map((inv) => {
                  const stockLevel = inv.quantity;
                  const statusColor = stockLevel > 100 ? 'success' : stockLevel > 50 ? 'warning' : 'danger';
                  const statusText = stockLevel > 100 ? 'In Stock' : stockLevel > 50 ? 'Low Stock' : 'Critical';
                  
                  return (
                    <tr key={inv.product_id}>
                      <td><strong>{getMaterialName(inv.product_id)}</strong></td>
                      <td><code>{inv.product_id.substring(0, 12)}...</code></td>
                      <td>
                        <strong style={{ fontSize: '1.1rem' }}>{inv.quantity.toFixed(2)}</strong>
                      </td>
                      <td>{new Date(inv.last_updated).toLocaleDateString()}</td>
                      <td>
                        <span className={`badge badge-${statusColor}`}>{statusText}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          ) : (
            <div style={{ padding: '60px', textAlign: 'center', color: '#757575' }}>
              <p>No inventory data available.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Inventory;
