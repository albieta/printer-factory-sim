import React, { useEffect, useState } from 'react';
import { Alert, Card, Table } from 'react-bootstrap';
import PageGuide from '../components/PageGuide';
import { getErrorMessage, retailerAPI } from '../services/api';
import type { RetailerCustomerOrder, RetailerPurchaseOrder, RetailerStockItem } from '../types';
import { onSimulationUpdate } from '../utils/simulationEvents';
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

  const loadData = async () => {
    try {
      setLoading(true);
      const [summaryRes, stockRes, ordersRes, purchasesRes] = await Promise.all([
        retailerAPI.getSummary(),
        retailerAPI.getStock(),
        retailerAPI.getOrders(),
        retailerAPI.getPurchases(),
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
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load retailer data.'));
    } finally {
      setLoading(false);
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
