import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Table } from 'react-bootstrap';
import { FaMinus, FaPlus, FaUserMinus, FaUserPlus } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import { configAPI, getErrorMessage, ordersAPI } from '../services/api';
import type { ManufacturingOrder, Product, SimulationConfig } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import { announceSimulationUpdate, onSimulationUpdate } from '../utils/simulationEvents';

const Production: React.FC = () => {
  const [releasedOrders, setReleasedOrders] = useState<ManufacturingOrder[]>([]);
  const [completedOrders, setCompletedOrders] = useState<ManufacturingOrder[]>([]);
  const [printers, setPrinters] = useState<Product[]>([]);
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [assemblyActionLoading, setAssemblyActionLoading] = useState(false);

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
      setError(getErrorMessage(err, 'Failed to load assembly data.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProduction();
    const clear = onSimulationUpdate(() => {
      void loadProduction();
    });

    return clear;
  }, []);

  const runAssemblyAction = async (action: () => Promise<unknown>, label: string) => {
    try {
      setAssemblyActionLoading(true);
      setError(null);
      await action();
      setMessage(`${label} — configuration updated.`);
      announceSimulationUpdate();
      await loadProduction();
    } catch (err) {
      setError(getErrorMessage(err, `Failed: ${label}`));
    } finally {
      setAssemblyActionLoading(false);
    }
  };

  const printerMap = useMemo(() => new Map(printers.map((printer) => [printer.id, printer])), [printers]);
  const queuedHours = releasedOrders.reduce((total, order) => total + order.quantity * (printerMap.get(order.product_id)?.assembly_hours ?? 0), 0);
  const completedHours = completedOrders.reduce((total, order) => total + order.quantity * (printerMap.get(order.product_id)?.assembly_hours ?? 0), 0);
  const effectiveHours = config?.effective_daily_assembly_hours ?? config?.daily_assembly_hours ?? 0;
  const capacityUse = effectiveHours ? Math.min((queuedHours / effectiveHours) * 100, 100) : 0;

  if (loading) {
    return <LoadingSpinner label="Loading assembly state..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Assembly</div>
          <h1>Manage shared production capacity</h1>
          <p>Released orders wait here until the simulator advances. Assembly uses one shared daily pool of hours derived from lines, workers per line, and shift length.</p>
        </div>
      </div>

      <PageGuide
        title="Assembly"
        controls="This screen shows the active manufacturing queue and explains how much shared assembly capacity those orders will consume when the next day runs."
        next="Orders that fit inside the available daily capacity complete when the simulation advances. Remaining released work stays queued for later days."
        tip="The simulator does not model individual worker assignments or separate production lanes yet. It uses one shared daily capacity pool, calculated as assembly lines × workers per line × worker hours."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success" dismissible onClose={() => setMessage(null)}>{message}</Alert> : null}

      <div className="kpi-grid">
        <div className="kpi-card info">
          <div className="kpi-label">Queued for Assembly</div>
          <div className="kpi-value">{releasedOrders.length}</div>
          <div className="kpi-subtext">Released orders waiting for the next production run</div>
        </div>
        <div className="kpi-card warning">
          <div className="kpi-label">Queued Assembly Hours</div>
          <div className="kpi-value">{queuedHours.toFixed(1)}</div>
          <div className="kpi-subtext">Hours demanded by released orders</div>
        </div>
        <div className="kpi-card success">
          <div className="kpi-label">Completed Hours</div>
          <div className="kpi-value">{completedHours.toFixed(1)}</div>
          <div className="kpi-subtext">Assembly hours already finished</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Queue Load</div>
          <div className="kpi-value">{capacityUse.toFixed(0)}%</div>
          <div className="kpi-subtext">Against {effectiveHours.toFixed(1)} shared hours per day</div>
        </div>
      </div>

      <div className="two-column">
        <div className="surface-panel card-body">
          <div className="section-title">
            <h4>Capacity model</h4>
          </div>
          <div className="metric-list">
            <div className="metric-item stat-row">
              <span>Assembly lines</span>
              <strong>{config?.assembly_lines ?? 0}</strong>
            </div>
            <div className="metric-item stat-row">
              <span>Workers per line</span>
              <strong>{config?.workers_per_line ?? 0}</strong>
            </div>
            <div className="metric-item stat-row">
              <span>Shift hours</span>
              <strong>{config?.shift_hours?.toFixed(1) ?? '0.0'}</strong>
            </div>
            <div className="metric-item emphasis-item">
              <div className="stat-row">
                <span>Derived daily assembly hours</span>
                <strong>{effectiveHours.toFixed(1)}</strong>
              </div>
              <div className="formula-line">{config?.assembly_lines ?? 0} lines × {config?.workers_per_line ?? 0} workers/line × {config?.shift_hours?.toFixed(1) ?? '0.0'} worker hours = {effectiveHours.toFixed(1)} shared hours/day</div>
            </div>
          </div>
        </div>

        <div className="surface-panel card-body">
          <div className="section-title">
            <h4>What this means operationally</h4>
          </div>
          <div className="list-stack">
            <div className="metric-item">
              <strong>Workers and lines define daily throughput.</strong>
              <div className="text-muted mt-2">Increase lines, workers per line, or shift hours in Configuration to create more daily assembly capacity.</div>
            </div>
            <div className="metric-item">
              <strong>Released orders compete for the same pool.</strong>
              <div className="text-muted mt-2">There is no separate scheduler per line yet, so all released orders draw from one shared batch of hours each day.</div>
            </div>
            <div className="metric-item">
              <strong>Status flow is simple and explicit.</strong>
              <div className="text-muted mt-2">Orders move from Awaiting Release to Queued for Production, then either Complete or switch to Blocked by Material Shortage if missing stock is detected when production tries to run.</div>
            </div>
          </div>
        </div>
      </div>

      <Card className="mb-4">
        <Card.Header>Workforce actions</Card.Header>
        <Card.Body>
          <p className="text-muted">
            Open or close assembly lines and hire or fire workers. Each action records a financial transaction and takes effect immediately.
          </p>
          <div className="two-column">
            <div className="metric-item">
              <strong>Assembly lines</strong>
              <div className="text-muted mt-1">Currently: {config?.assembly_lines ?? 0}</div>
              <div className="action-buttons mt-3">
                <Button
                  variant="success"
                  size="sm"
                  disabled={assemblyActionLoading}
                  onClick={() => void runAssemblyAction(() => configAPI.openLine(), 'Assembly line opened')}
                >
                  <FaPlus className="me-1" />Open line
                  {config?.cost_per_assembly_line ? ` — $${Number(config.cost_per_assembly_line).toLocaleString()}` : ''}
                </Button>
                <Button
                  variant="outline-danger"
                  size="sm"
                  disabled={assemblyActionLoading || (config?.assembly_lines ?? 1) <= 1}
                  onClick={() => void runAssemblyAction(() => configAPI.closeLine(), 'Assembly line closed')}
                >
                  <FaMinus className="me-1" />Close line
                </Button>
              </div>
            </div>
            <div className="metric-item">
              <strong>Workers per line</strong>
              <div className="text-muted mt-1">
                Currently: {config?.workers_per_line ?? 0} / {config?.max_workers_per_line ?? 0} max
              </div>
              <div className="action-buttons mt-3">
                <Button
                  variant="success"
                  size="sm"
                  disabled={assemblyActionLoading || (config?.workers_per_line ?? 0) >= (config?.max_workers_per_line ?? 10)}
                  onClick={() => void runAssemblyAction(() => configAPI.hireWorker(), 'Worker hired')}
                >
                  <FaUserPlus className="me-1" />Hire worker
                  {config?.cost_per_worker_per_hour ? ` — $${Number(config.cost_per_worker_per_hour)}/hr` : ''}
                </Button>
                <Button
                  variant="outline-danger"
                  size="sm"
                  disabled={assemblyActionLoading || (config?.workers_per_line ?? 1) <= 1}
                  onClick={() => void runAssemblyAction(() => configAPI.fireWorker(), 'Worker fired')}
                >
                  <FaUserMinus className="me-1" />Fire worker
                </Button>
              </div>
            </div>
          </div>
        </Card.Body>
      </Card>

      <div className="card mb-4">
        <div className="card-header">Released manufacturing orders</div>
        <div className="card-body p-0">
          {releasedOrders.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Reference</th>
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
                      <td><span className="mono">{order.reference_code ?? order.id}</span></td>
                      <td>{order.product_name ?? product?.name ?? order.product_id}</td>
                      <td>{order.quantity}</td>
                      <td>{((product?.assembly_hours ?? 0) * order.quantity).toFixed(1)}</td>
                      <td>{order.released_date ?? '-'}</td>
                      <td><span className="badge badge-released">{order.status_label ?? order.status}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">Release pending orders from Manufacturing Orders to populate the assembly queue.</div>
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
                  <th>Reference</th>
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
                      <td><span className="mono">{order.reference_code ?? order.id}</span></td>
                      <td>{order.product_name ?? product?.name ?? order.product_id}</td>
                      <td>{order.quantity}</td>
                      <td>{order.completed_date ?? '-'}</td>
                      <td>{((product?.assembly_hours ?? 0) * order.quantity).toFixed(1)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">Completed orders will appear here after the simulation advances through assembly.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Production;
