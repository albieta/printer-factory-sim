import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Table } from 'react-bootstrap';
import { FaClipboardCheck, FaEye } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import { getErrorMessage, ordersAPI } from '../services/api';
import type { BOMRequirements, ManufacturingOrder } from '../types';
import { OrderStatus } from '../types';
import { announceSimulationUpdate } from '../utils/simulationEvents';
import LoadingSpinner from '../components/LoadingSpinner';

const STATUS_FILTERS = [
  { value: 'ALL', label: 'All statuses' },
  { value: 'PENDING', label: 'Awaiting release' },
  { value: 'RELEASED', label: 'Queued for assembly' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'BLOCKED', label: 'Blocked by materials' },
];

const Orders: React.FC = () => {
  const [orders, setOrders] = useState<ManufacturingOrder[]>([]);
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
      const ordersRes = await ordersAPI.getManufacturingOrders(status === 'ALL' ? undefined : status);
      setOrders(ordersRes.data);
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

  const pendingOrders = orders.filter((order) => order.status === OrderStatus.PENDING);

  const blockedOrders = useMemo(
    () => orders.filter((order) => order.status === OrderStatus.BLOCKED).slice(0, 4),
    [orders]
  );

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
      const referenceById = new Map(orders.map((order) => [order.id, order.reference_code ?? order.id]));
      const failedLines = response.data.failed.map(
        (entry) => `${referenceById.get(entry.order_id) ?? entry.order_id}: ${entry.reason}`
      );
      const failedCount = response.data.failed.length;
      setReleaseMessage(
        failedCount
          ? `${response.data.successful.length} orders released. ${failedCount} blocked. ${failedLines.join(' | ')}`
          : `${response.data.successful.length} orders released into the assembly queue.`
      );
      setSelectedOrders([]);
      announceSimulationUpdate();
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

  const getStatusBadge = (order: ManufacturingOrder) => {
    const variants: Record<OrderStatus, string> = {
      PENDING: 'badge-pending',
      RELEASED: 'badge-released',
      COMPLETED: 'badge-completed',
      BLOCKED: 'badge-blocked',
    };

    return <span className={`badge ${variants[order.status]}`}>{order.status_label ?? order.status}</span>;
  };

  if (loading) {
    return <LoadingSpinner label="Loading manufacturing orders..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Manufacturing Orders</div>
          <h1>Review and release demand</h1>
          <p>Demand starts here. Review what customers are asking for, check material requirements, and release only the work that should enter the shared assembly queue.</p>
        </div>
      </div>

      <PageGuide
        title="Manufacturing orders"
        controls="This screen decides which demand becomes active production work. Releasing an order does not complete it immediately; it only makes the order eligible to consume materials and assembly capacity on future simulation days."
        next="Released work appears in Assembly. If materials are missing, the order becomes blocked and stays visible until inventory is replenished."
        tip="The status tells you where the order sits in the flow: Awaiting Release, Queued for Production, Completed, or Blocked by Material Shortage."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {releaseMessage ? <Alert variant="success">{releaseMessage}</Alert> : null}

      <div className="kpi-grid">
        <div className="kpi-card warning">
          <div className="kpi-label">Awaiting Release</div>
          <div className="kpi-value">{orders.filter((order) => order.status === OrderStatus.PENDING).length}</div>
          <div className="kpi-subtext">Demand waiting for planner review</div>
        </div>
        <div className="kpi-card info">
          <div className="kpi-label">Queued for Assembly</div>
          <div className="kpi-value">{orders.filter((order) => order.status === OrderStatus.RELEASED).length}</div>
          <div className="kpi-subtext">Orders drawing from daily shared capacity</div>
        </div>
        <div className="kpi-card success">
          <div className="kpi-label">Completed</div>
          <div className="kpi-value">{orders.filter((order) => order.status === OrderStatus.COMPLETED).length}</div>
          <div className="kpi-subtext">Finished manufacturing orders</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Blocked</div>
          <div className="kpi-value">{orders.filter((order) => order.status === OrderStatus.BLOCKED).length}</div>
          <div className="kpi-subtext">Orders stopped by missing materials</div>
        </div>
      </div>

      <div className="two-column">
        <Card>
          <Card.Header>Release manufacturing work</Card.Header>
          <Card.Body>
            <p className="text-muted">
              Releasing an order moves it from demand review into the assembly queue. The queue consumes one shared pool of daily assembly hours when the simulation advances.
            </p>
            {pendingOrders.length ? (
              <>
                <div className="list-stack mb-3">
                  {pendingOrders.slice(0, 10).map((order) => (
                    <label className="metric-item" key={order.id}>
                      <div className="stat-row align-start">
                        <div>
                          <strong>{order.reference_code ?? order.id}</strong>
                          <div className="mt-1">{order.product_name ?? order.product_id}</div>
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
              <div className="empty-state">No manufacturing orders are awaiting release right now.</div>
            )}
          </Card.Body>
        </Card>

        <Card>
          <Card.Header>Blocked work and material checks</Card.Header>
          <Card.Body>
            {selectedOrderId && requirements ? (
              <div className="list-stack mb-4">
                <div className="metric-item">
                  <div className="section-kicker">Selected order</div>
                  <h4 className="mb-1">{requirements.product_name}</h4>
                  <div className="text-muted mono">{orders.find((order) => order.id === selectedOrderId)?.reference_code ?? selectedOrderId}</div>
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
            ) : null}

            {blockedOrders.length ? (
              <div className="list-stack">
                {blockedOrders.map((order) => (
                  <div className="metric-item" key={order.id}>
                    <div className="stat-row">
                      <strong>{order.reference_code ?? order.id}</strong>
                      <span className="badge badge-blocked">{order.status_label ?? 'Blocked'}</span>
                    </div>
                    <div className="mt-2">{order.product_name ?? order.product_id}</div>
                    <div className="text-muted mt-2">{order.status_reason ?? 'Materials were not available at release time.'}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">No blocked orders right now. Open any order below to inspect the material draw before releasing it.</div>
            )}
            {inspecting ? <p className="text-muted mt-3 mb-0">Loading order requirements...</p> : null}
          </Card.Body>
        </Card>
      </div>

      <div className="card">
        <div className="card-header d-flex justify-content-between align-items-center gap-3 flex-wrap">
          <span>All manufacturing orders</span>
          <Form.Select style={{ maxWidth: 240 }} value={filter} onChange={(event) => setFilter(event.target.value)}>
            {STATUS_FILTERS.map((status) => (
              <option key={status.value} value={status.value}>{status.label}</option>
            ))}
          </Form.Select>
        </div>
        <div className="card-body p-0">
          {orders.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Product</th>
                  <th>Quantity</th>
                  <th>Status</th>
                  <th>Status Reason</th>
                  <th>Created</th>
                  <th>Released</th>
                  <th>Completed</th>
                  <th>Inspect</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td><span className="mono">{order.reference_code ?? order.id}</span></td>
                    <td>
                      <strong>{order.product_name ?? order.product_id}</strong>
                    </td>
                    <td>{order.quantity}</td>
                    <td>{getStatusBadge(order)}</td>
                    <td>{order.status_reason ?? '-'}</td>
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
