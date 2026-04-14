import React, { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';
import { Table, Badge, Card, Alert, Row, Col, Form } from 'react-bootstrap';
import { FaChartPie, FaChartLine } from 'react-icons/fa';
import { eventsAPI, exportAPI } from '../services/api';
import type { Event } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Reports: React.FC = () => {
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventFilter, setEventFilter] = useState<string>('all');

  const fetchEvents = async () => {
    try {
      setLoading(true);
      const response = await eventsAPI.getEvents({ limit: 500 });
      setEvents(response.data);
      setError(null);
    } catch (err: any) {
      setError('Failed to load events');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvents();
  }, []);

  const handleExport = async (type: 'full' | 'inventory' | 'events') => {
    try {
      let response;
      switch (type) {
        case 'full':
          response = await exportAPI.exportFullState();
          break;
        case 'inventory':
          response = await exportAPI.exportInventory();
          break;
        case 'events':
          response = await exportAPI.exportEvents();
          break;
      }
      
      // Create download link
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${type}_export_${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError('Failed to export data');
    }
  };

  const getEventCounts = () => {
    const counts: Record<string, number> = {};
    events.forEach(event => {
      counts[event.event_type] = (counts[event.event_type] || 0) + 1;
    });
    return counts;
  };

  if (loading) return <LoadingSpinner />;

  const eventCounts = getEventCounts();

  return (
    <div>
      <div className="page-header">
        <h1>Reports & Analytics</h1>
        <p>Analyze production performance and export data</p>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {/* Export Buttons */}
      <div className="action-bar mb-4">
        <h3>Data Export</h3>
        <div className="action-buttons">
          <Button variant="primary" onClick={() => handleExport('full')}>
            Export Full State
          </Button>
          <Button variant="success" onClick={() => handleExport('inventory')}>
            Export Inventory
          </Button>
          <Button variant="info" onClick={() => handleExport('events')}>
            Export Events
          </Button>
        </div>
      </div>

      {/* Charts */}
      <Row>
        <Col md={6}>
          <div className="chart-container">
            <h4 style={{ marginBottom: '20px', fontWeight: 600 }}>
              <FaChartPie /> Event Type Distribution
            </h4>
            {Object.keys(eventCounts).length > 0 ? (
              <Plot
                data={[
                  {
                    type: 'pie',
                    labels: Object.keys(eventCounts),
                    values: Object.values(eventCounts),
                    hole: 0.4,
                    marker: {
                      colors: [
                        '#1976d2', '#4caf50', '#ff9800', '#f44336', 
                        '#9c27b0', '#00bcd4', '#ffeb3b', '#795548',
                        '#607d8b', '#e91e63', '#3f51b5', '#009688'
                      ]
                    },
                    textinfo: 'label+percent',
                    textposition: 'outside',
                  }
                ]}
                layout={{ 
                  showlegend: false,
                  margin: { t: 20, b: 20, l: 20, r: 20 }
                }}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
            ) : (
              <p style={{ color: '#757575', textAlign: 'center', padding: '40px' }}>
                No events to display.
              </p>
            )}
          </div>
        </Col>

        <Col md={6}>
          <div className="chart-container">
            <h4 style={{ marginBottom: '20px', fontWeight: 600 }}>
              <FaChartLine /> Events Over Time
            </h4>
            {events.length > 0 ? (
              <Plot
                data={[
                  {
                    x: events.map(e => e.sim_date).sort(),
                    type: 'histogram',
                    xbins: { size: 1 },
                    marker: { color: '#1976d2' },
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
                No events to display.
              </p>
            )}
          </div>
        </Col>
      </Row>

      {/* Event Log */}
      <div className="card">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>Event Log</span>
          <Form.Select 
            style={{ width: '250px' }}
            value={eventFilter}
            onChange={(e) => setEventFilter(e.target.value)}
          >
            <option value="all">All Events</option>
            <option value="ORDER_CREATED">Order Created</option>
            <option value="ORDER_RELEASED">Order Released</option>
            <option value="ORDER_COMPLETED">Order Completed</option>
            <option value="PO_CREATED">PO Created</option>
            <option value="PO_DELIVERED">PO Delivered</option>
            <option value="MATERIAL_CONSUMED">Material Consumed</option>
            <option value="DAY_ADVANCED">Day Advanced</option>
          </Form.Select>
        </div>
        <div className="card-body p-0">
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
                {events
                  .filter(e => eventFilter === 'all' || e.event_type === eventFilter)
                  .slice(0, 100)
                  .map((event) => (
                    <tr key={event.id}>
                      <td>
                        <Badge bg="primary">{event.event_type}</Badge>
                      </td>
                      <td>{event.sim_date}</td>
                      <td>{new Date(event.timestamp).toLocaleString()}</td>
                      <td>
                        <code style={{ fontSize: '0.75rem' }}>
                          {event.details ? JSON.stringify(event.details).substring(0, 150) + '...' : '-'}
                        </code>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </Table>
          ) : (
            <div style={{ padding: '60px', textAlign: 'center', color: '#757575' }}>
              <p>No events recorded yet.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Reports;
