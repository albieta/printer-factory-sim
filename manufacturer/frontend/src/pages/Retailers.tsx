import React, { useEffect, useState } from 'react';
import { Alert, Badge, Button, Card, Form, Table } from 'react-bootstrap';
import PageGuide from '../components/PageGuide';
import { configAPI, getErrorMessage, retailerAPI, scenariosAPI } from '../services/api';
import type { RetailerCustomerOrder, RetailerPurchaseOrder, RetailerStockItem, ScenarioSummary } from '../types';
import { announceSimulationUpdate, onSimulationUpdate } from '../utils/simulationEvents';
import { formatCurrency } from '../utils/formatters';
import LoadingSpinner from '../components/LoadingSpinner';

const Retailers: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentDay, setCurrentDay] = useState(0);
  const [fulfilledCount, setFulfilledCount] = useState(0);
  const [backordered_count, setBackorderedCount] = useState(0);
  const [totalRevenue, setTotalRevenue] = useState(0);
  const [available, setAvailable] = useState(false);
  const [stockItems, setStockItems] = useState<RetailerStockItem[]>([]);
  const [customerOrders, setCustomerOrders] = useState<RetailerCustomerOrder[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<RetailerPurchaseOrder[]>([]);
  const [activeScenario, setActiveScenario] = useState<ScenarioSummary | null>(null);
  const [activeRunDay, setActiveRunDay] = useState<number | null>(null);
  const [demandForm, setDemandForm] = useState({
    retailer_demand_enabled: false,
    retailer_demand_mean: '8',
    retailer_demand_variance: '2',
    retailer_demand_modifier: '1',
    retailer_demand_base_price: '400',
  });
  const [demandSaving, setDemandSaving] = useState(false);
  const [demandMessage, setDemandMessage] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const [summaryRes, stockRes, ordersRes, purchasesRes, scenarioListRes, scenarioStatusRes, configRes] =
        await Promise.all([
          retailerAPI.getSummary(),
          retailerAPI.getStock(),
          retailerAPI.getOrders(),
          retailerAPI.getPurchases(),
          scenariosAPI.list().catch(() => null),
          scenariosAPI.status().catch(() => null),
          configAPI.getConfig().catch(() => null),
        ]);

      const summary = summaryRes.data;
      setAvailable(summary.available);
      setCurrentDay(summary.current_day);
      setFulfilledCount(summary.fulfilled_count);
      setBackorderedCount(summary.backordered_count);
      setTotalRevenue(summary.total_revenue);

      setStockItems(stockRes.data.items ?? []);
      setCustomerOrders(ordersRes.data.orders ?? []);
      setPurchaseOrders(purchasesRes.data.purchases ?? []);

      // Sync manual demand form from saved config.
      if (configRes) {
        const cfg = configRes.data;
        setDemandForm({
          retailer_demand_enabled: cfg.retailer_demand_enabled ?? false,
          retailer_demand_mean: String(cfg.retailer_demand_mean ?? 8),
          retailer_demand_variance: String(cfg.retailer_demand_variance ?? 2),
          retailer_demand_modifier: String(cfg.retailer_demand_modifier ?? 1),
          retailer_demand_base_price: String(cfg.retailer_demand_base_price ?? 400),
        });
      }

      // Resolve active scenario from status + list.
      const run = scenarioStatusRes?.data?.run ?? null;
      if (run && scenarioListRes) {
        const matched = scenarioListRes.data.scenarios.find(
          (s) => s.relative_path === run.scenario,
        ) ?? null;
        setActiveScenario(matched);
        setActiveRunDay(run.current_day);
      } else {
        setActiveScenario(null);
        setActiveRunDay(null);
      }

      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load retailer data.'));
    } finally {
      setLoading(false);
    }
  };

  const saveDemandConfig = async () => {
    try {
      setDemandSaving(true);
      await configAPI.updateConfig({
        retailer_demand_enabled: demandForm.retailer_demand_enabled,
        retailer_demand_mean: Number(demandForm.retailer_demand_mean),
        retailer_demand_variance: Number(demandForm.retailer_demand_variance),
        retailer_demand_modifier: Number(demandForm.retailer_demand_modifier),
        retailer_demand_base_price: Number(demandForm.retailer_demand_base_price),
      } as Parameters<typeof configAPI.updateConfig>[0]);
      setDemandMessage('Manual demand settings saved.');
      announceSimulationUpdate();
    } catch (err) {
      setDemandMessage(getErrorMessage(err, 'Failed to save demand settings.'));
    } finally {
      setDemandSaving(false);
    }
  };

  useEffect(() => {
    void loadData();
    const clear = onSimulationUpdate(() => {
      void loadData();
    });

    return clear;
  }, []);

  if (loading) {
    return <LoadingSpinner label="Loading retailer data..." />;
  }

  if (!available) {
    return (
      <div>
        <div className="page-header">
          <div>
            <div className="section-kicker">Retailers</div>
            <h1>Monitor retailer operations and demand</h1>
            <p>The retailer is currently offline. Check the retailer service and try again.</p>
          </div>
        </div>

        <Alert variant="danger">
          <strong>Retailer offline.</strong> The retailer service is not responding. Start the retailer service at the configured URL and try again.
        </Alert>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Retailers</div>
          <h1>Monitor the retailer's business and demand</h1>
          <p>Track retailer inventory, customer orders, and purchase orders to the manufacturer. Understand customer demand and retailer stock levels to coordinate supply.</p>
        </div>
      </div>

      <PageGuide
        title="Retailers"
        controls="The retailer sells to customers and purchases finished goods from you. Monitor stock levels and customer orders to understand demand pressure."
        next="Stock levels increase when you deliver SalesOrders to the retailer. Customer backlogs consume retailer stock. PurchaseOrders from retailer to you appear here as they move through their lifecycle."
        tip="Low retailer stock = high risk of stockouts. High backordered customer orders = pent-up demand that you could fulfill if inventory was available."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {/* ── How demand works ── */}
      <Card className="mb-4">
        <Card.Header><strong>How Customer Demand Works</strong></Card.Header>
        <Card.Body>
          <p className="mb-2">
            Each simulated day the turn engine generates synthetic customer orders and POSTs them to
            this retailer before any agent acts. Orders are <strong>one printer per customer</strong>
            — there are no multi-model baskets.
          </p>
          <p className="mb-2">
            The number of orders placed for each model is drawn independently from a normal
            distribution:
          </p>
          <pre className="bg-light rounded p-3 mb-3" style={{ fontSize: '0.85rem' }}>
{`orders_per_model = max(0, round(gauss(
    mean × demand_modifier × price_factor,
    sqrt(variance)
)))

price_factor = max(0.2, 1 − (retail_price − base_price) / base_price)`}
          </pre>
          <ul className="mb-2">
            <li>
              <strong>mean / variance</strong> — set in the scenario's <code>base_demand</code>{' '}
              block; doubled values are now the active baseline.
            </li>
            <li>
              <strong>demand_modifier</strong> — multiplied from all events active on that day
              (events compound, so overlapping events multiply together).
            </li>
            <li>
              <strong>price_factor</strong> — automatically reduces demand when the retailer agent
              raises prices above the scenario's base price. Floored at 0.2 to prevent total
              collapse.
            </li>
            <li>
              <strong>Reproducibility</strong> — each day is seeded with <code>random.seed(day)</code>,
              so identical scenario runs produce identical demand sequences.
            </li>
          </ul>
          <p className="mb-0 text-muted" style={{ fontSize: '0.85rem' }}>
            Fulfilled orders consume retailer stock immediately. Backordered orders queue until
            the retailer receives a delivery from the manufacturer.
          </p>
        </Card.Body>
      </Card>

      {/* ── Active scenario configuration ── */}
      <Card className="mb-4">
        <Card.Header><strong>Active Scenario — Demand Configuration</strong></Card.Header>
        <Card.Body>
          {activeScenario ? (
            <>
              <div className="d-flex align-items-center gap-3 mb-3 flex-wrap">
                <span>
                  <strong>Scenario:</strong>{' '}
                  {activeScenario.scenario_name ?? activeScenario.name}
                </span>
                {activeScenario.base_demand && (
                  <>
                    <span>
                      <strong>Base mean:</strong> {activeScenario.base_demand.mean} orders/model/day
                    </span>
                    <span>
                      <strong>Variance:</strong> {activeScenario.base_demand.variance}
                    </span>
                  </>
                )}
                {activeScenario.base_price != null && (
                  <span>
                    <strong>Base price:</strong> {formatCurrency(activeScenario.base_price)}
                  </span>
                )}
                {activeRunDay != null && (
                  <span className="text-muted">Day {activeRunDay} of run</span>
                )}
              </div>
              {activeScenario.events && activeScenario.events.length > 0 && (
                <Table responsive hover size="sm" className="mb-0">
                  <thead>
                    <tr>
                      <th>Event</th>
                      <th>Days</th>
                      <th>Demand ×</th>
                      <th>Supply ×</th>
                      <th>Lead time ×</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeScenario.events.map((ev, idx) => {
                      const isActive =
                        activeRunDay != null &&
                        ev.start_day != null &&
                        ev.end_day != null &&
                        activeRunDay >= ev.start_day &&
                        activeRunDay <= ev.end_day;
                      return (
                        <tr key={idx} className={isActive ? 'table-warning' : ''}>
                          <td>
                            <strong>{ev.name ?? '—'}</strong>
                            {isActive && (
                              <Badge bg="warning" text="dark" className="ms-2">
                                active
                              </Badge>
                            )}
                          </td>
                          <td className="text-nowrap">
                            {ev.start_day ?? '?'}–{ev.end_day ?? '?'}
                          </td>
                          <td>{ev.demand_modifier != null ? `×${ev.demand_modifier}` : '—'}</td>
                          <td>{ev.supply_modifier != null ? `×${ev.supply_modifier}` : '—'}</td>
                          <td>{ev.lead_time_modifier != null ? `×${ev.lead_time_modifier}` : '—'}</td>
                          <td className="text-muted" style={{ fontSize: '0.85rem' }}>
                            {ev.description ?? '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </Table>
              )}
            </>
          ) : (
            <p className="text-muted mb-0">
              No scenario is currently running. Start one from the{' '}
              <a href="/scenarios">Scenarios</a> tab to see demand configuration here.
            </p>
          )}
        </Card.Body>
      </Card>

      {/* ── Manual demand configuration ── */}
      <Card className="mb-4">
        <Card.Header>
          <strong>Manual Demand Configuration</strong>
          <span className="text-muted ms-2" style={{ fontSize: '0.85rem' }}>
            — applies when Advance Day is clicked without a running scenario
          </span>
        </Card.Header>
        <Card.Body>
          {demandMessage && (
            <Alert variant={demandMessage.startsWith('Failed') ? 'danger' : 'success'} dismissible onClose={() => setDemandMessage(null)}>
              {demandMessage}
            </Alert>
          )}
          <Form.Group className="mb-3 d-flex align-items-center gap-3">
            <Form.Check
              type="switch"
              id="retailer-demand-switch"
              label={demandForm.retailer_demand_enabled ? 'Inject customer orders on every manual Advance Day' : 'Customer order injection disabled'}
              checked={demandForm.retailer_demand_enabled}
              onChange={(e) => setDemandForm({ ...demandForm, retailer_demand_enabled: e.target.checked })}
            />
          </Form.Group>
          <div className="two-column">
            <Form.Group className="mb-3">
              <Form.Label>Mean orders per model per day</Form.Label>
              <Form.Control
                type="number" min="0" step="1"
                value={demandForm.retailer_demand_mean}
                disabled={!demandForm.retailer_demand_enabled}
                onChange={(e) => setDemandForm({ ...demandForm, retailer_demand_mean: e.target.value })}
              />
              <Form.Text>
                Centre of the Gaussian draw for each printer model. Corresponds to <code>base_demand.mean</code> in scenario files (current scenario default: 8–10).
              </Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Variance</Form.Label>
              <Form.Control
                type="number" min="0" step="0.5"
                value={demandForm.retailer_demand_variance}
                disabled={!demandForm.retailer_demand_enabled}
                onChange={(e) => setDemandForm({ ...demandForm, retailer_demand_variance: e.target.value })}
              />
              <Form.Text>
                Daily noise around the mean. Standard deviation = √variance. Typical scenario value: 1–2.
              </Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Demand modifier</Form.Label>
              <Form.Control
                type="number" min="0.1" step="0.1"
                value={demandForm.retailer_demand_modifier}
                disabled={!demandForm.retailer_demand_enabled}
                onChange={(e) => setDemandForm({ ...demandForm, retailer_demand_modifier: e.target.value })}
              />
              <Form.Text>
                Multiplies the mean. 1.0 = baseline. 2.0 = doubled demand. Equivalent to a scenario event's <code>demand_modifier</code>.
              </Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Base price for price sensitivity (£)</Form.Label>
              <Form.Control
                type="number" min="0" step="50"
                value={demandForm.retailer_demand_base_price}
                disabled={!demandForm.retailer_demand_enabled}
                onChange={(e) => setDemandForm({ ...demandForm, retailer_demand_base_price: e.target.value })}
              />
              <Form.Text>
                Price at which demand is unaffected. If the retailer charges more than this, demand automatically decreases (floored at ×0.2). Matches <code>base_price</code> in scenario files (default: 400).
              </Form.Text>
            </Form.Group>
          </div>
          <div className="d-flex align-items-center gap-3 mt-2">
            <Button variant="primary" onClick={() => void saveDemandConfig()} disabled={demandSaving}>
              {demandSaving ? 'Saving…' : 'Save demand settings'}
            </Button>
            {demandForm.retailer_demand_enabled && (
              <span className="text-muted" style={{ fontSize: '0.85rem' }}>
                Expected: ~{(Number(demandForm.retailer_demand_mean) * Number(demandForm.retailer_demand_modifier)).toFixed(1)} orders/model/day (before price factor)
              </span>
            )}
          </div>
        </Card.Body>
      </Card>

      <div className="kpi-grid">
        <div className="kpi-card info">
          <div className="kpi-label">Current Day</div>
          <div className="kpi-value">{currentDay}</div>
          <div className="kpi-subtext">Retailer's simulated day</div>
        </div>
        <div className="kpi-card success">
          <div className="kpi-label">Fulfilled Orders</div>
          <div className="kpi-value">{fulfilledCount}</div>
          <div className="kpi-subtext">Customer orders completed</div>
        </div>
        <div className="kpi-card warning">
          <div className="kpi-label">Backordered</div>
          <div className="kpi-value">{backordered_count}</div>
          <div className="kpi-subtext">Awaiting stock or delivery</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Total Revenue</div>
          <div className="kpi-value">{formatCurrency(totalRevenue)}</div>
          <div className="kpi-subtext">From fulfilled orders</div>
        </div>
      </div>

      {/* Section 1: Retailer Stock */}
      <h2 className="mt-5 mb-3">Stock Levels</h2>
      <p className="text-muted mb-3">
        <strong>Retailer's available inventory.</strong> These finished goods came from your SalesOrders.
        Stock decreases as customer orders are fulfilled.
      </p>
      <Card className="mb-4">
        <Card.Body className="p-0">
          {stockItems.length ? (
            <Table responsive hover className="mb-0">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Quantity</th>
                </tr>
              </thead>
              <tbody>
                {stockItems.map((item, idx) => (
                  <tr key={idx}>
                    <td><strong>{item.product_name}</strong></td>
                    <td>{item.quantity} units</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state p-4">No stock on hand. Complete SalesOrders to replenish retailer inventory.</div>
          )}
        </Card.Body>
      </Card>

      {/* Section 2: Customer Orders */}
      <h2 className="mt-5 mb-3">Customer Orders</h2>
      <p className="text-muted mb-3">
        <strong>Orders from the retailer's customers.</strong> These are the end-demand signals.
        FULFILLED means the retailer had stock. BACKORDERED means demand exceeded inventory.
      </p>
      <Card className="mb-4">
        <Card.Body className="p-0">
          {customerOrders.length ? (
            <Table responsive hover className="mb-0">
              <thead>
                <tr>
                  <th>Order ID</th>
                  <th>Product</th>
                  <th>Quantity</th>
                  <th>Status</th>
                  <th>Placed (Day)</th>
                  <th>Fulfilled (Day)</th>
                  <th>Revenue</th>
                </tr>
              </thead>
              <tbody>
                {customerOrders.map((order) => (
                  <tr key={order.id}>
                    <td><span className="mono">{order.id}</span></td>
                    <td>{order.product ?? '—'}</td>
                    <td>{order.quantity}</td>
                    <td>
                      <span
                        className={`badge ${
                          order.status === 'FULFILLED'
                            ? 'badge-completed'
                            : order.status === 'BACKORDERED'
                              ? 'badge-blocked'
                              : 'badge-pending'
                        }`}
                      >
                        {order.status}
                      </span>
                    </td>
                    <td>{order.placed_day ?? '—'}</td>
                    <td>{order.fulfilled_day ?? '—'}</td>
                    <td>{formatCurrency(order.total_price ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state p-4">No customer orders yet.</div>
          )}
        </Card.Body>
      </Card>

      {/* Section 3: Purchase Orders to Manufacturer */}
      <h2 className="mt-5 mb-3">Purchase Orders</h2>
      <p className="text-muted mb-3">
        <strong>Orders the retailer placed with you.</strong> These are triggered when retailer demand exceeds stock.
        Track them alongside your SalesOrders to understand the connection.
      </p>
      <Card className="mb-4">
        <Card.Body className="p-0">
          {purchaseOrders.length ? (
            <Table responsive hover className="mb-0">
              <thead>
                <tr>
                  <th>PO ID</th>
                  <th>Product</th>
                  <th>Quantity</th>
                  <th>Status</th>
                  <th>Placed (Day)</th>
                  <th>Expected (Day)</th>
                  <th>Delivered (Day)</th>
                </tr>
              </thead>
              <tbody>
                {purchaseOrders.map((po) => (
                  <tr key={po.id}>
                    <td><span className="mono">{po.id}</span></td>
                    <td>{po.product_name ?? '—'}</td>
                    <td>{po.quantity}</td>
                    <td>
                      <span
                        className={`badge ${
                          po.status === 'DELIVERED'
                            ? 'badge-completed'
                            : po.status === 'REJECTED'
                              ? 'badge-blocked'
                              : 'badge-pending'
                        }`}
                      >
                        {po.status}
                      </span>
                    </td>
                    <td>{po.placed_day ?? '—'}</td>
                    <td>{po.expected_delivery_day ?? '—'}</td>
                    <td>{po.delivered_day ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state p-4">No purchase orders placed yet.</div>
          )}
        </Card.Body>
      </Card>
    </div>
  );
};

export default Retailers;
