import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Badge, Table } from 'react-bootstrap';
import { configAPI, getErrorMessage, ordersAPI } from '../services/api';
import type { ManufacturingOrder, Product, SimulationConfig } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Production: React.FC = () => {
  const [releasedOrders, setReleasedOrders] = useState<ManufacturingOrder[]>([]);
  const [completedOrders, setCompletedOrders] = useState<ManufacturingOrder[]>([]);
  const [printers, setPrinters] = useState<Product[]>([]);
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProduction = async () => {
    try {
      setLoading(true);
      const [releasedRes, completedRes, printersRes, configRes] = await Promise.all([
        ordersAPI.getManufacturingOrders('RELEASED'),
        ordersAPI.getManufacturingOrders('COMPLETED'),
        configAPI.getPrinterModels(),
        configAPI.getConfig(),
      ]);
      setReleasedOrders(releasedRes.data);
      setCompletedOrders(completedRes.data);
      setPrinters(printersRes.data);
      setConfig(configRes.data);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load production data.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProduction();
  }, []);

  const printerMap = useMemo(() => new Map(printers.map((printer) => [printer.id, printer])), [printers]);
  const queuedHours = releasedOrders.reduce((total, order) => total + order.quantity * (printerMap.get(order.product_id)?.assembly_hours ?? 0), 0);
  const completedHours = completedOrders.reduce((total, order) => total + order.quantity * (printerMap.get(order.product_id)?.assembly_hours ?? 0), 0);
  const capacityUse = config?.daily_assembly_hours ? Math.min((queuedHours / config.daily_assembly_hours) * 100, 100) : 0;

  if (loading) {
    return <LoadingSpinner label="Loading production state..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Production</div>
          <h1>Line status</h1>
          <p>Check what is already released, how much assembly time the queue demands, and which products have recently cleared the factory floor.</p>
        </div>
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="kpi-grid">
        <div className="kpi-card info">
          <div className="kpi-label">Released Orders</div>
          <div className="kpi-value">{releasedOrders.length}</div>
          <div className="kpi-subtext">Currently queued for the next production run</div>
        </div>
        <div className="kpi-card warning">
          <div className="kpi-label">Queued Assembly Hours</div>
          <div className="kpi-value">{queuedHours.toFixed(1)}</div>
          <div className="kpi-subtext">Hours demanded by released orders</div>
        </div>
        <div className="kpi-card success">
          <div className="kpi-label">Completed Orders</div>
          <div className="kpi-value">{completedOrders.length}</div>
          <div className="kpi-subtext">Orders finished so far</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Daily Capacity Use</div>
          <div className="kpi-value">{capacityUse.toFixed(0)}%</div>
          <div className="kpi-subtext">Against {config?.daily_assembly_hours ?? 0} configured hours/day</div>
        </div>
      </div>

      <div className="two-column">
        <div className="surface-panel card-body">
          <div className="section-title">
            <h4>Capacity pressure</h4>
          </div>
          <div className="metric-list">
            <div className="metric-item stat-row">
              <span>Configured daily assembly hours</span>
              <strong>{config?.daily_assembly_hours ?? 0}</strong>
            </div>
            <div className="metric-item stat-row">
              <span>Queued hours waiting to run</span>
              <strong>{queuedHours.toFixed(1)}</strong>
            </div>
            <div className="metric-item stat-row">
              <span>Hours already completed</span>
              <strong>{completedHours.toFixed(1)}</strong>
            </div>
            <div className="metric-item">
              <div className="stat-row">
                <span>Queue load ratio</span>
                <strong>{capacityUse.toFixed(1)}%</strong>
              </div>
              <div className="progress-shell mt-2">
                <div className="progress-fill" style={{ width: `${capacityUse}%` }} />
              </div>
            </div>
          </div>
        </div>

        <div className="surface-panel card-body">
          <div className="section-title">
            <h4>Product mix in queue</h4>
          </div>
          <div className="list-stack">
            {releasedOrders.length ? releasedOrders.map((order) => {
              const product = printerMap.get(order.product_id);
              return (
                <div key={order.id} className="metric-item">
                  <div className="stat-row">
                    <strong>{product?.name ?? order.product_id.slice(0, 8)}</strong>
                    <Badge className="badge-released">RELEASED</Badge>
                  </div>
                  <div className="text-muted mt-2">
                    Qty {order.quantity} · {((product?.assembly_hours ?? 0) * order.quantity).toFixed(1)} assembly hours
                  </div>
                </div>
              );
            }) : <div className="empty-state">No orders are currently released into production.</div>}
          </div>
        </div>
      </div>

      <div className="card mb-4">
        <div className="card-header">Released production orders</div>
        <div className="card-body p-0">
          {releasedOrders.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Product</th>
                  <th>Quantity</th>
                  <th>Assembly Hours</th>
                  <th>Released Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {releasedOrders.map((order) => {
                  const product = printerMap.get(order.product_id);
                  return (
                    <tr key={order.id}>
                      <td><span className="mono">{order.id.slice(0, 8)}</span></td>
                      <td>{product?.name ?? order.product_id}</td>
                      <td>{order.quantity}</td>
                      <td>{((product?.assembly_hours ?? 0) * order.quantity).toFixed(1)}</td>
                      <td>{order.released_date ?? '-'}</td>
                      <td><Badge className="badge-released">{order.status}</Badge></td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">Release pending orders from the Orders screen to populate the production queue.</div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">Recently completed work</div>
        <div className="card-body p-0">
          {completedOrders.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Product</th>
                  <th>Quantity</th>
                  <th>Completed Date</th>
                  <th>Assembly Hours</th>
                </tr>
              </thead>
              <tbody>
                {completedOrders.slice(-12).reverse().map((order) => {
                  const product = printerMap.get(order.product_id);
                  return (
                    <tr key={order.id}>
                      <td><span className="mono">{order.id.slice(0, 8)}</span></td>
                      <td>{product?.name ?? order.product_id}</td>
                      <td>{order.quantity}</td>
                      <td>{order.completed_date ?? '-'}</td>
                      <td>{((product?.assembly_hours ?? 0) * order.quantity).toFixed(1)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">Completed orders will appear here after the simulation advances through production.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Production;
