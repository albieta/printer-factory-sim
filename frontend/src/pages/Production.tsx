import React, { useState, useEffect } from 'react';
import { Table, Badge, Card, Alert, Row, Col } from 'react-bootstrap';
import { FaIndustry } from 'react-icons/fa';
import { ordersAPI } from '../services/api';
import type { ManufacturingOrder } from '../types';
import { OrderStatus } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Production: React.FC = () => {
  const [activeOrders, setActiveOrders] = useState<ManufacturingOrder[]>([]);
  const [completedToday, setCompletedToday] = useState<ManufacturingOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProductionData = async () => {
    try {
      setLoading(true);
      const [activeRes, completedRes] = await Promise.all([
        ordersAPI.getManufacturingOrders('RELEASED'),
        ordersAPI.getManufacturingOrders('COMPLETED'),
      ]);
      setActiveOrders(activeRes.data);
      setCompletedToday(completedRes.data.slice(-10)); // Last 10 completed
      setError(null);
    } catch (err: any) {
      setError('Failed to load production data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProductionData();
  }, []);

  if (loading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1>Production Status</h1>
        <p>Monitor active production orders and capacity utilization</p>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {/* Active Production */}
      <Row className="mb-4">
        <Col md={12}>
          <div className="kpi-card">
            <div className="kpi-label">Active Production Orders</div>
            <div className="kpi-value"><FaIndustry /></div>
            <div className="kpi-subtext">{activeOrders.length} orders in production</div>
          </div>
        </Col>
      </Row>

      {/* Active Orders Table */}
      <div className="card mb-4">
        <div className="card-header">
          <strong>Active Production Orders</strong>
        </div>
        <div className="card-body p-0">
          {activeOrders.length > 0 ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Order ID</th>
                  <th>Product ID</th>
                  <th>Quantity</th>
                  <th>Status</th>
                  <th>Released Date</th>
                </tr>
              </thead>
              <tbody>
                {activeOrders.map((order) => (
                  <tr key={order.id}>
                    <td><code>{order.id.substring(0, 12)}...</code></td>
                    <td><code>{order.product_id.substring(0, 12)}...</code></td>
                    <td><strong>{order.quantity}</strong></td>
                    <td><Badge className="badge-released">{order.status}</Badge></td>
                    <td>{order.released_date || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div style={{ padding: '60px', textAlign: 'center', color: '#757575' }}>
              <p>No active production orders. Release pending orders to start production.</p>
            </div>
          )}
        </div>
      </div>

      {/* Recently Completed */}
      <div className="card">
        <div className="card-header">
          <strong>Recently Completed Orders</strong>
        </div>
        <div className="card-body p-0">
          {completedToday.length > 0 ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Order ID</th>
                  <th>Product ID</th>
                  <th>Quantity</th>
                  <th>Status</th>
                  <th>Completed Date</th>
                </tr>
              </thead>
              <tbody>
                {completedToday.map((order) => (
                  <tr key={order.id}>
                    <td><code>{order.id.substring(0, 12)}...</code></td>
                    <td><code>{order.product_id.substring(0, 12)}...</code></td>
                    <td><strong>{order.quantity}</strong></td>
                    <td><Badge className="badge-completed">{order.status}</Badge></td>
                    <td>{order.completed_date || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div style={{ padding: '60px', textAlign: 'center', color: '#757575' }}>
              <p>No completed orders yet. Production orders will appear here once completed.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Production;
