import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Row, Col, Table } from 'react-bootstrap';
import { FaDollarSign, FaSave, FaUndo, FaChartLine } from 'react-icons/fa';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import PageGuide from '../components/PageGuide';
import LoadingSpinner from '../components/LoadingSpinner';
import { financialAPI, getErrorMessage } from '../services/api';
import type { FinancialSummary, FinancialTransaction } from '../services/api';
import type { SimulationConfig } from '../types';
import { announceSimulationUpdate, onSimulationUpdate } from '../utils/simulationEvents';

interface FormData {
  cost_per_assembly_line: string;
  cost_per_worker_per_hour: string;
  max_workers_per_line: string;
}

const Financial: React.FC = () => {
  const [summary, setSummary] = useState<FinancialSummary | null>(null);
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [transactions, setTransactions] = useState<FinancialTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState<FormData>({
    cost_per_assembly_line: '50000',
    cost_per_worker_per_hour: '50',
    max_workers_per_line: '10',
  });

  const loadData = async () => {
    try {
      setLoading(true);
      const [summaryRes, configRes, transactionsRes] = await Promise.all([
        financialAPI.getSummary(),
        financialAPI.getConfig(),
        financialAPI.getTransactions(),
      ]);
      setSummary(summaryRes.data);
      setConfig(configRes.data);
      setTransactions(transactionsRes.data);
      setFormData({
        cost_per_assembly_line: String(summaryRes.data.cost_per_assembly_line),
        cost_per_worker_per_hour: String(summaryRes.data.cost_per_worker_per_hour),
        max_workers_per_line: String(summaryRes.data.max_workers_per_line),
      });
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load financial data.'));
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

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const saveConfig = async () => {
    try {
      setSaving(true);
      await financialAPI.updateConfig({
        cost_per_assembly_line: parseFloat(formData.cost_per_assembly_line),
        cost_per_worker_per_hour: parseFloat(formData.cost_per_worker_per_hour),
        max_workers_per_line: parseInt(formData.max_workers_per_line, 10),
      });
      setMessage('Configuration saved successfully.');
      void loadData();
      announceSimulationUpdate();
      setTimeout(() => setMessage(null), 3000);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to save configuration.'));
    } finally {
      setSaving(false);
    }
  };

  const restoreCurrentValues = () => {
    if (!summary) return;
    setFormData({
      cost_per_assembly_line: String(summary.cost_per_assembly_line),
      cost_per_worker_per_hour: String(summary.cost_per_worker_per_hour),
      max_workers_per_line: String(summary.max_workers_per_line),
    });
  };

  const transactionsByDay = useMemo(() => {
    const grouped = new Map<number, FinancialTransaction[]>();
    transactions.forEach((tx) => {
      if (!grouped.has(tx.sim_day)) {
        grouped.set(tx.sim_day, []);
      }
      grouped.get(tx.sim_day)!.push(tx);
    });
    return grouped;
  }, [transactions]);

  const chartData = useMemo(() => {
    const days = Array.from(transactionsByDay.keys()).sort((a, b) => a - b);
    const data: Array<{ day: number; costs: number; revenue: number; profit: number }> = [];

    let cumulativeCosts = 0;
    let cumulativeRevenue = 0;

    days.forEach((day) => {
      const dayTransactions = transactionsByDay.get(day) || [];
      const dayCosts = dayTransactions
        .filter((tx) => tx.amount < 0)
        .reduce((sum, tx) => sum + Math.abs(tx.amount), 0);
      const dayRevenue = dayTransactions
        .filter((tx) => tx.amount > 0)
        .reduce((sum, tx) => sum + tx.amount, 0);

      cumulativeCosts += dayCosts;
      cumulativeRevenue += dayRevenue;

      data.push({
        day,
        costs: cumulativeCosts,
        revenue: cumulativeRevenue,
        profit: cumulativeRevenue - cumulativeCosts,
      });
    });

    return data;
  }, [transactionsByDay]);

  if (loading) return <LoadingSpinner />;

  const formatCurrency = (value: number) => new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);

  return (
    <div className="page-container">
      <PageGuide
        icon={<FaDollarSign />}
        title="Financial Management"
        description="Configure costs and monitor financial status"
      />

      {message && <Alert variant="success">{message}</Alert>}
      {error && <Alert variant="danger">{error}</Alert>}

      {summary && (
        <>
          {/* Summary Cards */}
          <Row className="mb-4">
            <Col md={3}>
              <Card className="shadow-sm">
                <Card.Body className="text-center">
                  <h6 className="text-muted mb-2">Total Costs</h6>
                  <h3 className="text-danger">{formatCurrency(summary.total_costs)}</h3>
                </Card.Body>
              </Card>
            </Col>
            <Col md={3}>
              <Card className="shadow-sm">
                <Card.Body className="text-center">
                  <h6 className="text-muted mb-2">Total Revenue</h6>
                  <h3 className="text-success">{formatCurrency(summary.total_revenue)}</h3>
                </Card.Body>
              </Card>
            </Col>
            <Col md={3}>
              <Card className="shadow-sm">
                <Card.Body className="text-center">
                  <h6 className="text-muted mb-2">Net Profit</h6>
                  <h3 className={summary.net_profit >= 0 ? 'text-info' : 'text-warning'}>
                    {formatCurrency(summary.net_profit)}
                  </h3>
                </Card.Body>
              </Card>
            </Col>
            <Col md={3}>
              <Card className="shadow-sm">
                <Card.Body className="text-center">
                  <h6 className="text-muted mb-2">Profit Margin</h6>
                  <h3 className="text-primary">
                    {summary.total_revenue > 0
                      ? ((summary.net_profit / summary.total_revenue) * 100).toFixed(1)
                      : '0'}
                    %
                  </h3>
                </Card.Body>
              </Card>
            </Col>
          </Row>

          {/* Configuration Section */}
          <Card className="shadow-sm mb-4">
            <Card.Header className="bg-light">
              <Card.Title className="mb-0">Cost Configuration</Card.Title>
            </Card.Header>
            <Card.Body>
              <Form>
                <Form.Group className="mb-3">
                  <Form.Label>Cost per Assembly Line ($)</Form.Label>
                  <Form.Control
                    type="number"
                    name="cost_per_assembly_line"
                    value={formData.cost_per_assembly_line}
                    onChange={handleInputChange}
                    min="0"
                    step="1000"
                  />
                  <Form.Text className="text-muted">Cost incurred when opening a new assembly line</Form.Text>
                </Form.Group>

                <Form.Group className="mb-3">
                  <Form.Label>Cost per Worker per Hour ($)</Form.Label>
                  <Form.Control
                    type="number"
                    name="cost_per_worker_per_hour"
                    value={formData.cost_per_worker_per_hour}
                    onChange={handleInputChange}
                    min="0"
                    step="10"
                  />
                  <Form.Text className="text-muted">Hourly wage cost when hiring a worker</Form.Text>
                </Form.Group>

                <Form.Group className="mb-3">
                  <Form.Label>Max Workers per Line</Form.Label>
                  <Form.Control
                    type="number"
                    name="max_workers_per_line"
                    value={formData.max_workers_per_line}
                    onChange={handleInputChange}
                    min="1"
                    step="1"
                  />
                  <Form.Text className="text-muted">Maximum workers allowed per assembly line</Form.Text>
                </Form.Group>

                <div className="d-flex gap-2">
                  <Button variant="primary" onClick={saveConfig} disabled={saving}>
                    <FaSave className="me-2" />
                    {saving ? 'Saving...' : 'Save Changes'}
                  </Button>
                  <Button variant="outline-secondary" onClick={restoreCurrentValues}>
                    <FaUndo className="me-2" />
                    Restore
                  </Button>
                </div>
              </Form>
            </Card.Body>
          </Card>

          {/* Chart Section */}
          {chartData.length > 0 && (
            <Card className="shadow-sm mb-4">
              <Card.Header className="bg-light">
                <Card.Title className="mb-0">
                  <FaChartLine className="me-2" />
                  Financial Evolution
                </Card.Title>
              </Card.Header>
              <Card.Body>
                <ResponsiveContainer width="100%" height={350}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="day" label={{ value: 'Simulation Day', position: 'insideBottomRight', offset: -5 }} />
                    <YAxis label={{ value: 'Amount ($)', angle: -90, position: 'insideLeft' }} />
                    <Tooltip formatter={(value: number) => formatCurrency(value)} />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="costs"
                      stroke="#dc3545"
                      name="Cumulative Costs"
                      connectNulls
                    />
                    <Line
                      type="monotone"
                      dataKey="revenue"
                      stroke="#28a745"
                      name="Cumulative Revenue"
                      connectNulls
                    />
                    <Line
                      type="monotone"
                      dataKey="profit"
                      stroke="#0dcaf0"
                      name="Net Profit"
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Card.Body>
            </Card>
          )}

          {/* Transactions Table */}
          <Card className="shadow-sm">
            <Card.Header className="bg-light">
              <Card.Title className="mb-0">Transaction History</Card.Title>
            </Card.Header>
            <Card.Body>
              <div className="table-responsive">
                <Table striped bordered hover size="sm">
                  <thead>
                    <tr>
                      <th>Day</th>
                      <th>Type</th>
                      <th>Amount</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.length > 0 ? (
                      transactions.map((tx, idx) => (
                        <tr key={idx}>
                          <td>{tx.sim_day}</td>
                          <td>
                            <span
                              className={`badge ${
                                tx.amount < 0 ? 'bg-danger' : 'bg-success'
                              }`}
                            >
                              {tx.type}
                            </span>
                          </td>
                          <td className={tx.amount < 0 ? 'text-danger' : 'text-success'}>
                            {formatCurrency(tx.amount)}
                          </td>
                          <td>{tx.description}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={4} className="text-center text-muted">
                          No transactions yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </Table>
              </div>
            </Card.Body>
          </Card>
        </>
      )}
    </div>
  );
};

export default Financial;
