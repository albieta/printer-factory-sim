import React, { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';
import { Button, Row, Col, Alert, Table, Badge } from 'react-bootstrap';
import { FaPlayCircle, FaCalendarAlt } from 'react-icons/fa';
import { simulationAPI, eventsAPI } from '../services/api';
import type { SimulationStatus, Event } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Overview: React.FC = () => {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [advancing, setAdvancing] = useState(false);
  const [advanceResult, setAdvanceResult] = useState<{date: string; created: number; completed: number} | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [statusRes, eventsRes] = await Promise.all([
        simulationAPI.getStatus(),
        eventsAPI.getEvents({ limit: 50 }),
      ]);
      setStatus(statusRes.data);
      setEvents(eventsRes.data);
      setError(null);
    } catch (err: any) {
      setError('Failed to load simulation data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleAdvanceDay = async () => {
    try {
      setAdvancing(true);
      const result = await simulationAPI.advanceDay();
      setAdvanceResult({
        date: result.data.sim_date,
        created: result.data.orders_created,
        completed: result.data.orders_completed,
      });
      await fetchData();
    } catch (err: any) {
      setError('Failed to advance day');
    } finally {
      setAdvancing(false);
    }
  };

  if (loading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1>Overview</h1>
        <p>Monitor your 3D printer production simulation</p>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}
      {advanceResult && (
        <Alert variant="success">
          <strong>Day Advanced!</strong> Simulation date is now {advanceResult.date}. 
          Created {advanceResult.created} orders, completed {advanceResult.completed} orders.
        </Alert>
      )}

      {/* KPI Cards */}
      <Row>
        <Col md={3}>
          <div className="kpi-card info">
            <div className="kpi-label">Current Date</div>
            <div className="kpi-value">
              <FaCalendarAlt style={{ fontSize: '2rem' }} />
            </div>
            <div className="kpi-subtext">{status?.current_date}</div>
          </div>
        </Col>
        <Col md={3}>
          <div className="kpi-card warning">
            <div className="kpi-label">Pending Orders</div>
            <div className="kpi-value">{status?.pending_orders || 0}</div>
            <div className="kpi-subtext">Awaiting production</div>
          </div>
        </Col>
        <Col md={3}>
          <div className="kpi-card success">
            <div className="kpi-label">Completed Orders</div>
            <div className="kpi-value">{status?.completed_orders || 0}</div>
            <div className="kpi-subtext">Successfully produced</div>
          </div>
        </Col>
        <Col md={3}>
          <div className="kpi-card">
            <div className="kpi-label">Total Events</div>
            <div className="kpi-value">{status?.total_events || 0}</div>
            <div className="kpi-subtext">Simulation events logged</div>
          </div>
        </Col>
      </Row>

      {/* Simulation Control */}
      <div className="action-bar">
        <h3>Simulation Control</h3>
        <div className="action-buttons">
          <Button 
            variant="primary" 
            size="lg"
            onClick={handleAdvanceDay}
            disabled={advancing}
          >
            <FaPlayCircle /> {advancing ? 'Advancing...' : 'Advance Day'}
          </Button>
        </div>
      </div>

      {/* Charts */}
      <Row>
        <Col md={12}>
          <div className="chart-container">
            <h4 style={{ marginBottom: '20px', fontWeight: 600 }}>Event Activity Over Time</h4>
            {events.length > 0 ? (
              <Plot
                data={[
                  {
                    x: events.map(e => e.sim_date),
                    type: 'histogram',
                    xbins: { start: events.length > 0 ? events[events.length - 1].sim_date : '', end: events.length > 0 ? events[0].sim_date : '', size: 1 },
                    marker: { color: '#1976d2' },
                    name: 'Events'
                  }
                ]}
                layout={{
                  xaxis: { title: 'Date' },
                  yaxis: { title: 'Number of Events' },
                  showlegend: false,
                  margin: { t: 20, b: 50, l: 50, r: 20 }
                }}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
            ) : (
              <p style={{ color: '#757575', textAlign: 'center', padding: '40px' }}>
                No events yet. Advance the simulation to generate events.
              </p>
            )}
          </div>
        </Col>
      </Row>

      {/* Recent Events */}
      <div className="card">
        <div className="card-header">Recent Events</div>
        <div className="card-body">
          {events.length > 0 ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Event Type</th>
                  <th>Simulation Date</th>
                  <th>Timestamp</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 20).map((event) => (
                  <tr key={event.id}>
                    <td>
                      <Badge bg="primary">{event.event_type}</Badge>
                    </td>
                    <td>{event.sim_date}</td>
                    <td>{new Date(event.timestamp).toLocaleString()}</td>
                    <td>
                      <code style={{ fontSize: '0.8rem' }}>
                        {event.details ? JSON.stringify(event.details).substring(0, 100) + '...' : '-'}
                      </code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <p style={{ color: '#757575', textAlign: 'center', padding: '40px' }}>
              No events recorded yet.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default Overview;
