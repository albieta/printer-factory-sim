import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Table } from 'react-bootstrap';
import { FaBan, FaClipboardCheck, FaEye } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import { getErrorMessage, ordersAPI, salesOrdersAPI } from '../services/api';
import type { SalesOrder } from '../services/api';
import type { BOMRequirements, ManufacturingOrder } from '../types';
import { OrderStatus } from '../types';
import { announceSimulationUpdate, onSimulationUpdate } from '../utils/simulationEvents';
import LoadingSpinner from '../components/LoadingSpinner';

const STATUS_FILTERS = [
  { value: 'ALL', label: 'All statuses' },
  { value: 'PENDING', label: 'Awaiting release' },
  { value: 'RELEASED', label: 'Queued for production' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'BLOCKED', label: 'Blocked by materials' },
  { value: 'REJECTED', label: 'Rejected' },
];

const ORDER_STATUS_GUIDE = [
  {
    badgeClass: 'badge-pending',
    label: 'Awaiting Release',
    description: 'Demand is waiting for planner review and has not entered the assembly queue yet.',
  },
  {
    badgeClass: 'badge-released',
    label: 'Queued for Production',
    description: 'The order is accepted and waiting to consume shared assembly capacity.',
  },
  {
    badgeClass: 'badge-blocked',
    label: 'Awaiting Release but Blocked by Material Shortage',
    description: 'The planner tried to release it, but required materials were not available.',
  },
  {
    badgeClass: 'badge-blocked',
    label: 'Queued for Production but Blocked by Material Shortage',
    description: 'The order had already been accepted, but production later found a material shortage.',
  },
  {
    badgeClass: 'badge-completed',
    label: 'Completed',
    description: 'Assembly finished and the order is no longer active work.',
  },
  {
    badgeClass: 'badge-neutral',
    label: 'Rejected',
    description: 'The planner declined the order while keeping its history visible.',
  },
];

const Orders: React.FC = () => {
  const [orders, setOrders] = useState<ManufacturingOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('ALL');
  const [selectedOrders, setSelectedOrders] = useState<string[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [requirements, setRequirements] = useState<BOMRequirements | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [salesOrders, setSalesOrders] = useState<SalesOrder[]>([]);
  const [salesOrdersLoading, setSalesOrdersLoading] = useState(true);

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

  const loadSalesOrders = async () => {
    try {
      setSalesOrdersLoading(true);
      const res = await salesOrdersAPI.list('PENDING');
      setSalesOrders(res.data);
    } catch {
      // non-critical — retailer may be offline
      setSalesOrders([]);
    } finally {
      setSalesOrdersLoading(false);
    }
  };

  useEffect(() => {
    void loadOrders(filter);
    void loadSalesOrders();
    const clear = onSimulationUpdate(() => {
      void loadOrders(filter);
      void loadSalesOrders();
    });

    return clear;
  }, [filter]);

  const pendingOrders = useMemo(
    () => orders.filter((order) => order.status === OrderStatus.PENDING),
    [orders]
  );
  const blockedOrders = useMemo(
    () => orders.filter((order) => order.status === OrderStatus.BLOCKED),
    [orders]
  );

  const allPendingSelected = pendingOrders.length > 0 && pendingOrders.every((order) => selectedOrders.includes(order.id));

  const loadRequirements = async (order: ManufacturingOrder) => {
    if (selectedOrderId === order.id) {
      setSelectedOrderId(null);
      setRequirements(null);
      return;
    }

    try {
      setInspecting(true);
      setSelectedOrderId(order.id);
      const response = await ordersAPI.getOrderRequirements(order.id);
      setRequirements(response.data);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load bill of materials for that order.'));
    } finally {
      setInspecting(false);
    }
  };

  const buildActionMessage = (
    actionLabel: string,
    successful: string[],
    failed: Array<{ order_id: string; reason: string }>
  ) => {
    const referenceById = new Map(orders.map((order) => [order.id, order.reference_code ?? order.id]));
    const failedLines = failed.map(
      (entry) => `${referenceById.get(entry.order_id) ?? entry.order_id}: ${entry.reason}`
    );
    return failed.length
      ? `${successful.length} orders ${actionLabel}. ${failed.length} failed. ${failedLines.join(' | ')}`
      : `${successful.length} orders ${actionLabel}.`;
  };

  const handleReleaseOrders = async () => {
    if (!selectedOrders.length) {
      return;
    }

    try {
      const response = await ordersAPI.releaseOrders({ order_ids: selectedOrders });
      setActionMessage(buildActionMessage('released into the assembly queue', response.data.successful, response.data.failed));
      setSelectedOrders([]);
      announceSimulationUpdate();
      await loadOrders(filter);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to release the selected orders.'));
    }
  };

  const handleRejectOrders = async () => {
    if (!selectedOrders.length) {
      return;
    }

    try {
      const response = await ordersAPI.rejectOrders({ order_ids: selectedOrders });
      setActionMessage(buildActionMessage('rejected during review', response.data.successful, response.data.failed));
      setSelectedOrders([]);
      announceSimulationUpdate();
      await loadOrders(filter);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to reject the selected orders.'));
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

  const toggleAllPendingOrders = () => {
    setSelectedOrders((current) => {
      if (allPendingSelected) {
        return current.filter((id) => !pendingOrders.some((order) => order.id === id));
      }
      const next = new Set(current);
      pendingOrders.forEach((order) => next.add(order.id));
      return [...next];
    });
  };

  const handleReleaseSalesOrder = async (id: string) => {
    try {
      await salesOrdersAPI.release(id);
      setActionMessage('Retailer order accepted and queued for production.');
      announceSimulationUpdate();
      await Promise.all([loadOrders(filter), loadSalesOrders()]);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to release retailer order.'));
    }
  };

  const handleRejectSalesOrder = async (id: string) => {
    try {
      await salesOrdersAPI.reject(id, 'Rejected by planner');
      setActionMessage('Retailer order rejected.');
      announceSimulationUpdate();
      await loadSalesOrders();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to reject retailer order.'));
    }
  };

  const getStatusBadge = (order: ManufacturingOrder) => {
    const variants: Record<OrderStatus, string> = {
      PENDING: 'badge-pending',
      RELEASED: 'badge-released',
      COMPLETED: 'badge-completed',
      BLOCKED: 'badge-blocked',
      REJECTED: 'badge-neutral',
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
          <p>Demand starts here. Review what customers are asking for, inspect the BOM inline, and choose whether each order should be accepted into assembly or rejected.</p>
        </div>
      </div>

      <PageGuide
        title="Manufacturing orders"
        controls="This screen is where planners decide which demand becomes accepted factory work. Releasing moves an order into the assembly queue, while rejecting closes it out without deleting history."
        next="Released work appears in Assembly. If materials are missing, the order becomes blocked and can return automatically once inventory is replenished."
        tipLabel="Order statuses"
        tip={(
          <div className="status-grid order-status-guide">
            {ORDER_STATUS_GUIDE.map((status) => (
              <div className="metric-item" key={status.label}>
                <span className={`badge ${status.badgeClass}`}>{status.label}</span>
                <div className="text-muted mt-2">{status.description}</div>
              </div>
            ))}
            <div className="metric-item">
              <strong>Screen behavior</strong>
              <div className="text-muted mt-2">Blocked orders and BOM checks are shown separately on purpose so shortage recovery and material inspection do not compete for the same space.</div>
            </div>
          </div>
        )}
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {actionMessage ? <Alert variant="success">{actionMessage}</Alert> : null}

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
        <div className="kpi-card">
          <div className="kpi-label">Rejected</div>
          <div className="kpi-value">{orders.filter((order) => order.status === OrderStatus.REJECTED).length}</div>
          <div className="kpi-subtext">Demand declined during review</div>
        </div>
      </div>

      <Card className="mb-4">
        <Card.Header>
          <span>Retailer orders — awaiting decision</span>
          {salesOrders.length > 0 && (
            <span className="badge badge-pending ms-2">{salesOrders.length}</span>
          )}
        </Card.Header>
        <Card.Body>
          {salesOrdersLoading ? (
            <p className="text-muted mb-0">Loading retailer orders…</p>
          ) : salesOrders.length ? (
            <Table responsive hover className="mb-0">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Retailer</th>
                  <th>Product</th>
                  <th>Qty</th>
                  <th>Unit price</th>
                  <th>Total</th>
                  <th>Placed day</th>
                  <th>Exp. ship day</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {salesOrders.map((so) => (
                  <tr key={so.id}>
                    <td><span className="mono">{so.reference_code}</span></td>
                    <td>{so.retailer}</td>
                    <td><strong>{so.model ?? '—'}</strong></td>
                    <td>{so.quantity}</td>
                    <td>£{so.unit_price}</td>
                    <td>£{so.total_price}</td>
                    <td>{so.placed_day}</td>
                    <td>{so.expected_ship_day ?? '—'}</td>
                    <td>
                      <div className="d-flex gap-2">
                        <Button
                          variant="success"
                          size="sm"
                          onClick={() => void handleReleaseSalesOrder(so.id)}
                        >
                          <FaClipboardCheck className="me-1" />Accept
                        </Button>
                        <Button
                          variant="outline-danger"
                          size="sm"
                          onClick={() => void handleRejectSalesOrder(so.id)}
                        >
                          <FaBan className="me-1" />Reject
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">No pending retailer orders awaiting a decision.</div>
          )}
        </Card.Body>
      </Card>

      <div className="two-column">
        <Card>
          <Card.Header>Planner decision queue</Card.Header>
          <Card.Body>
            <p className="text-muted">
              Accepted orders enter the shared assembly queue. Rejected orders remain in history but are excluded from accepted-demand calculations and active work.
            </p>
            {pendingOrders.length ? (
              <>
                <div className="action-buttons mb-3">
                  <Button variant="outline-secondary" onClick={toggleAllPendingOrders}>
                    {allPendingSelected ? 'Clear selected orders' : 'Select all orders'}
                  </Button>
                </div>
                <div className="list-stack scroll-list planner-queue-list mb-3">
                  {pendingOrders.map((order) => (
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
                <div className="action-buttons">
                  <Button variant="success" onClick={handleReleaseOrders} disabled={!selectedOrders.length}>
                    <FaClipboardCheck className="me-2" />
                    Release {selectedOrders.length} selected
                  </Button>
                  <Button variant="outline-danger" onClick={handleRejectOrders} disabled={!selectedOrders.length}>
                    <FaBan className="me-2" />
                    Reject {selectedOrders.length} selected
                  </Button>
                </div>
              </>
            ) : (
              <div className="empty-state">No manufacturing orders are awaiting release right now.</div>
            )}
          </Card.Body>
        </Card>

        <Card>
          <Card.Header>Blocked by material shortage</Card.Header>
          <Card.Body>
            {blockedOrders.length ? (
              <div className="list-stack scroll-list blocked-queue-list">
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
              <div className="empty-state">No blocked orders right now.</div>
            )}
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
                {orders.map((order) => {
                  const isExpanded = selectedOrderId === order.id;
                  return (
                    <React.Fragment key={order.id}>
                      <tr>
                        <td><span className="mono">{order.reference_code ?? order.id}</span></td>
                        <td><strong>{order.product_name ?? order.product_id}</strong></td>
                        <td>{order.quantity}</td>
                        <td>{getStatusBadge(order)}</td>
                        <td>{order.status_reason ?? '-'}</td>
                        <td>{order.created_date}</td>
                        <td>{order.released_date ?? '-'}</td>
                        <td>{order.completed_date ?? '-'}</td>
                        <td>
                          <Button variant="outline-secondary" size="sm" onClick={() => void loadRequirements(order)}>
                            <FaEye className="me-2" />
                            {isExpanded ? 'Hide BOM' : 'BOM'}
                          </Button>
                        </td>
                      </tr>
                      {isExpanded ? (
                        <tr className="inline-detail-row">
                          <td colSpan={9}>
                            <div className="inline-detail-panel">
                              <div className="section-kicker">Material check</div>
                              <h4>{requirements?.product_name ?? order.product_name ?? order.product_id}</h4>
                              {inspecting ? (
                                <p className="text-muted mb-0">Loading order requirements...</p>
                              ) : requirements?.requirements.length ? (
                                <div className="list-stack">
                                  {requirements.requirements.map((requirement) => (
                                    <div className="metric-item" key={requirement.material_id}>
                                      <div className="stat-row">
                                        <strong>{requirement.material_name}</strong>
                                        <span className="badge badge-neutral">{requirement.total_required.toFixed(2)} required</span>
                                      </div>
                                      <div className="text-muted mt-2">{requirement.quantity_per_unit.toFixed(2)} per finished unit</div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="empty-state">This product has no BOM entries yet.</div>
                              )}
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </React.Fragment>
                  );
                })}
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
