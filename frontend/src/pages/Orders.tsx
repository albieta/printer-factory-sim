import React, { useState, useEffect } from 'react';
import { Button, Table, Badge, Form, Alert, Row, Col, Card } from 'react-bootstrap';
import { FaClipboardCheck, FaEye } from 'react-icons/fa';
import { ordersAPI } from '../services/api';
import type { ManufacturingOrder } from '../types';
import { OrderStatus } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Orders: React.FC = () => {
  const [orders, setOrders] = useState<ManufacturingOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('ALL');
  const [selectedOrders, setSelectedOrders] = useState<string[]>([]);
  const [releaseResult, setReleaseResult] = useState<{successful: number; failed: Array<{order_id: string; reason: string}>} | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchOrders = async (status?: string) => {
    try {
      setLoading(true);
      const response = await ordersAPI.getManufacturingOrders(status === 'ALL' ? undefined : status);
      setOrders(response.data);
      setError(null);
    } catch (err: any) {
      setError('Failed to load orders');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders(filter);
  }, [filter]);

  const handleReleaseOrders = async () => {
    if (selectedOrders.length === 0) return;
    
    try {
      const response = await ordersAPI.releaseOrders({ order_ids: selectedOrders });
      setReleaseResult({
        successful: response.data.successful.length,
        failed: response.data.failed,
      });
      setSelectedOrders([]);
      await fetchOrders(filter);
    } catch (err: any) {
      setError('Failed to release orders');
    }
  };

  const getStatusBadge = (status: OrderStatus) => {
    const variants: Record<OrderStatus, string> = {
      PENDING: 'badge-pending',
      RELEASED: 'badge-released',
      COMPLETED: 'badge-completed',
      BLOCKED: 'badge-blocked',
    };
    return <Badge className={variants[status]}>{status}</Badge>;
  };

  const pendingOrders = orders.filter(o => o.status === OrderStatus.PENDING);

  if (loading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1>Manufacturing Orders</h1>
        <p>Manage customer orders for 3D printers</p>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}
      {releaseResult && (
        <Alert variant="success">
          <strong>Release Complete!</strong> {releaseResult.successful} orders released successfully.
          {releaseResult.failed.length > 0 && (
            <div style={{ marginTop: '10px' }}>
              Failed releases:
              <ul>
                {releaseResult.failed.map((f, i) => (
                  <li key={i}>{f.order_id}: {f.reason}</li>
                ))}
              </ul>
            </div>
          )}
        </Alert>
      )}

      {/* Release Orders Card */}
      {pendingOrders.length > 0 && (
        <Card className="mb-4">
          <Card.Header>
            <strong>Release Orders to Production</strong>
          </Card.Header>
          <Card.Body>
            <p>Select pending orders to release to production:</p>
            <div style={{ maxHeight: '200px', overflowY: 'auto', marginBottom: '16px' }}>
              {pendingOrders.map(order => (
                <Form.Check
                  key={order.id}
                  type="checkbox"
                  id={`order-${order.id}`}
                  label={`Order ${order.id.substring(0, 8)} - ${order.product_id.substring(0, 8)} (Qty: ${order.quantity})`}
                  checked={selectedOrders.includes(order.id)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectedOrders([...selectedOrders, order.id]);
                    } else {
                      setSelectedOrders(selectedOrders.filter(id => id !== order.id));
                    }
                  }}
                />
              ))}
            </div>
            <Button 
              variant="success" 
              onClick={handleReleaseOrders}
              disabled={selectedOrders.length === 0}
            >
              <FaClipboardCheck /> Release Selected Orders ({selectedOrders.length})
            </Button>
          </Card.Body>
        </Card>
      )}

      {/* Orders Table */}
      <div className="card">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>Orders</span>
          <Form.Select 
            style={{ width: '200px' }}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="ALL">All Status</option>
            <option value="PENDING">Pending</option>
            <option value="RELEASED">Released</option>
            <option value="COMPLETED">Completed</option>
            <option value="BLOCKED">Blocked</option>
          </Form.Select>
        </div>
        <div className="card-body p-0">
          {orders.length > 0 ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Order ID</th>
                  <th>Product</th>
                  <th>Quantity</th>
                  <th>Status</th>
                  <th>Created Date</th>
                  <th>Released Date</th>
                  <th>Completed Date</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td><code>{order.id.substring(0, 12)}...</code></td>
                    <td>{order.product_id.substring(0, 12)}...</td>
                    <td><strong>{order.quantity}</strong></td>
                    <td>{getStatusBadge(order.status)}</td>
                    <td>{order.created_date}</td>
                    <td>{order.released_date || '-'}</td>
                    <td>{order.completed_date || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div style={{ padding: '60px', textAlign: 'center', color: '#757575' }}>
              <p>No orders found{filter !== 'ALL' ? ` with status "${filter}"` : ''}.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Orders;
