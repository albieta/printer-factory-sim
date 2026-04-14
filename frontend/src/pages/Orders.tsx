import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Badge, Button, Card, Form, Table } from 'react-bootstrap';
import { FaClipboardCheck, FaEye } from 'react-icons/fa';
import { configAPI, getErrorMessage, ordersAPI } from '../services/api';
import type { BOMRequirements, ManufacturingOrder, Product } from '../types';
import { OrderStatus } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Orders: React.FC = () => {
  const [orders, setOrders] = useState<ManufacturingOrder[]>([]);
  const [printers, setPrinters] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('ALL');
  const [selectedOrders, setSelectedOrders] = useState<string[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [requirements, setRequirements] = useState<BOMRequirements | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [releaseMessage, setReleaseMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadOrders = async (status?: string) => {
    try {
      setLoading(true);
      const [ordersRes, printersRes] = await Promise.all([
        ordersAPI.getManufacturingOrders(status === 'ALL' ? undefined : status),
        configAPI.getPrinterModels(),
      ]);
      setOrders(ordersRes.data);
      setPrinters(printersRes.data);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load manufacturing orders.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOrders(filter);
  }, [filter]);

  const printerMap = useMemo(
    () => new Map(printers.map((printer) => [printer.id, printer.name])),
    [printers]
  );

  const pendingOrders = orders.filter((order) => order.status === OrderStatus.PENDING);

  const openRequirements = async (order: ManufacturingOrder) => {
    try {
      setInspecting(true);
      setSelectedOrderId(order.id);
      const response = await ordersAPI.getOrderRequirements(order.id);
      setRequirements(response.data);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load bill of materials for that order.'));
    } finally {
      setInspecting(false);
    }
  };

  const handleReleaseOrders = async () => {
    if (!selectedOrders.length) {
      return;
    }

    try {
      const response = await ordersAPI.releaseOrders({ order_ids: selectedOrders });
      const failedCount = response.data.failed.length;
      setReleaseMessage(
        `${response.data.successful.length} orders released${failedCount ? `, ${failedCount} blocked.` : '.'}`
      );
      setSelectedOrders([]);
      await loadOrders(filter);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to release the selected orders.'));
    }
  };

  const toggleOrder = (orderId: string, checked: boolean) => {
    setSelectedOrders((current) => {
      if (checked) {
        return [...current, orderId];
      }
      return current.filter((id) => id !== orderId);
    });
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

  if (loading) {
    return <LoadingSpinner label="Loading manufacturing orders..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Orders</div>
          <h1>Manufacturing queue</h1>
          <p>Release demand into production, inspect material requirements, and watch for blocked work before the line stalls.</p>
        </div>
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {releaseMessage ? <Alert variant="success">{releaseMessage}</Alert> : null}

      <div className="kpi-grid">
        <div className="kpi-card warning">
          <div className="kpi-label">Pending</div>
          <div className="kpi-value">{orders.filter((order) => order.status === OrderStatus.PENDING).length}</div>
          <div className="kpi-subtext">Orders ready for release review</div>
        </div>
        <div className="kpi-card info">
          <div className="kpi-label">Released</div>
          <div className="kpi-value">{orders.filter((order) => order.status === OrderStatus.RELEASED).length}</div>
          <div className="kpi-subtext">Currently in the production queue</div>
        </div>
        <div className="kpi-card success">
          <div className="kpi-label">Completed</div>
          <div className="kpi-value">{orders.filter((order) => order.status === OrderStatus.COMPLETED).length}</div>
          <div className="kpi-subtext">Finished and recorded</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Blocked</div>
          <div className="kpi-value">{orders.filter((order) => order.status === OrderStatus.BLOCKED).length}</div>
          <div className="kpi-subtext">Orders missing materials at release time</div>
        </div>
      </div>

      <div className="two-column">
        <Card>
          <Card.Header>Release pending work</Card.Header>
          <Card.Body>
            {pendingOrders.length ? (
              <>
                <p className="text-muted">Choose one or more pending orders to move into production.</p>
                <div className="list-stack mb-3">
                  {pendingOrders.slice(0, 10).map((order) => (
                    <label className="metric-item" key={order.id}>
                      <div className="stat-row">
                        <div>
                          <strong>{printerMap.get(order.product_id) ?? order.product_id.slice(0, 8)}</strong>
                          <div className="text-muted mono mt-1">{order.id}</div>
                        </div>
                        <Form.Check
                          checked={selectedOrders.includes(order.id)}
                          onChange={(event) => toggleOrder(order.id, event.target.checked)}
                        />
                      </div>
                      <div className="text-muted mt-2">Quantity {order.quantity} created on {order.created_date}</div>
                    </label>
                  ))}
                </div>
                <Button variant="success" onClick={handleReleaseOrders} disabled={!selectedOrders.length}>
                  <FaClipboardCheck className="me-2" />
                  Release {selectedOrders.length} selected orders
                </Button>
              </>
            ) : (
              <div className="empty-state">No pending orders are waiting for release right now.</div>
            )}
          </Card.Body>
        </Card>

        <Card>
          <Card.Header>Order material requirements</Card.Header>
          <Card.Body>
            {selectedOrderId && requirements ? (
              <div className="list-stack">
                <div className="metric-item">
                  <div className="section-kicker">Selected order</div>
                  <h4 className="mb-1">{requirements.product_name}</h4>
                  <div className="text-muted mono">{selectedOrderId}</div>
                </div>
                {requirements.requirements.length ? (
                  requirements.requirements.map((requirement) => (
                    <div className="metric-item" key={requirement.material_id}>
                      <div className="stat-row">
                        <strong>{requirement.material_name}</strong>
                        <span className="badge badge-neutral">{requirement.total_required.toFixed(2)} required</span>
                      </div>
                      <div className="text-muted mt-2">{requirement.quantity_per_unit.toFixed(2)} per finished unit</div>
                    </div>
                  ))
                ) : (
                  <div className="empty-state">This product has no BOM entries yet.</div>
                )}
              </div>
            ) : (
              <div className="empty-state">Open an order to inspect the exact material draw before releasing it.</div>
            )}
            {inspecting ? <p className="text-muted mt-3 mb-0">Loading order requirements...</p> : null}
          </Card.Body>
        </Card>
      </div>

      <div className="card">
        <div className="card-header d-flex justify-content-between align-items-center gap-3 flex-wrap">
          <span>All manufacturing orders</span>
          <Form.Select style={{ maxWidth: 220 }} value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="ALL">All statuses</option>
            <option value="PENDING">Pending</option>
            <option value="RELEASED">Released</option>
            <option value="COMPLETED">Completed</option>
            <option value="BLOCKED">Blocked</option>
          </Form.Select>
        </div>
        <div className="card-body p-0">
          {orders.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Product</th>
                  <th>Quantity</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Released</th>
                  <th>Completed</th>
                  <th>Inspect</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td><span className="mono">{order.id.slice(0, 8)}</span></td>
                    <td>
                      <strong>{printerMap.get(order.product_id) ?? order.product_id.slice(0, 8)}</strong>
                    </td>
                    <td>{order.quantity}</td>
                    <td>{getStatusBadge(order.status)}</td>
                    <td>{order.created_date}</td>
                    <td>{order.released_date ?? '-'}</td>
                    <td>{order.completed_date ?? '-'}</td>
                    <td>
                      <Button variant="outline-secondary" size="sm" onClick={() => void openRequirements(order)}>
                        <FaEye className="me-2" />
                        BOM
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">No orders found for the selected filter.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Orders;
