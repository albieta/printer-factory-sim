import React, { useEffect, useMemo, useState } from 'react';
import Plot from 'react-plotly.js';
import { Alert, Button, Form, Table } from 'react-bootstrap';
import { FaChartLine, FaChartPie, FaDownload } from 'react-icons/fa';
import { eventsAPI, exportAPI, getErrorMessage } from '../services/api';
import type { Event } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Reports: React.FC = () => {
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventFilter, setEventFilter] = useState('all');

  const loadEvents = async () => {
    try {
      setLoading(true);
      const response = await eventsAPI.getEvents({ limit: 500 });
      setEvents(response.data);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load event analytics.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadEvents();
  }, []);

  const filteredEvents = useMemo(
    () => events.filter((event) => eventFilter === 'all' || event.event_type === eventFilter),
    [eventFilter, events]
  );

  const eventCounts = useMemo(() => {
    const counts = new Map<string, number>();
    filteredEvents.forEach((event) => {
      counts.set(event.event_type, (counts.get(event.event_type) ?? 0) + 1);
    });
    return Array.from(counts.entries());
  }, [filteredEvents]);

  const activityByDate = useMemo(() => {
    const counts = new Map<string, number>();
    [...filteredEvents].reverse().forEach((event) => {
      counts.set(event.sim_date, (counts.get(event.sim_date) ?? 0) + 1);
    });
    return Array.from(counts.entries());
  }, [filteredEvents]);

  const handleExport = async (type: 'full' | 'inventory' | 'events') => {
    try {
      const response = type === 'full'
        ? await exportAPI.exportFullState()
        : type === 'inventory'
          ? await exportAPI.exportInventory()
          : await exportAPI.exportEvents();
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${type}_export_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to export report data.'));
    }
  };

  if (loading) {
    return <LoadingSpinner label="Loading reports and analytics..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Reports</div>
          <h1>Analytics and exports</h1>
          <p>Review the operational history, isolate specific event types, and export the simulator state for comparison across scenarios.</p>
        </div>
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="action-bar">
        <div>
          <div className="section-kicker">Data exports</div>
          <h3 className="mb-1">Download current simulator data</h3>
          <p className="text-muted mb-0">Use full-state exports for scenario snapshots and smaller exports for targeted analysis.</p>
        </div>
        <div className="action-buttons">
          <Button variant="primary" onClick={() => void handleExport('full')}><FaDownload className="me-2" />Full state</Button>
          <Button variant="success" onClick={() => void handleExport('inventory')}><FaDownload className="me-2" />Inventory</Button>
          <Button variant="warning" onClick={() => void handleExport('events')}><FaDownload className="me-2" />Events</Button>
        </div>
      </div>

      <div className="two-column">
        <div className="chart-container">
          <div className="section-title">
            <h4><FaChartPie className="me-2" />Event distribution</h4>
          </div>
          {eventCounts.length ? (
            <Plot
              data={[
                {
                  type: 'pie',
                  labels: eventCounts.map(([label]) => label),
                  values: eventCounts.map(([, value]) => value),
                  hole: 0.45,
                  marker: { colors: ['#be5b2d', '#1a6b67', '#d18a1a', '#b6463b', '#2f7d4a', '#705649', '#9d824f'] },
                  textinfo: 'label+percent',
                },
              ]}
              layout={{ paper_bgcolor: 'transparent', margin: { t: 10, r: 10, b: 10, l: 10 }, showlegend: false }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: '320px' }}
            />
          ) : (
            <div className="empty-state">No events match the current filter.</div>
          )}
        </div>

        <div className="chart-container">
          <div className="section-title">
            <h4><FaChartLine className="me-2" />Activity over time</h4>
          </div>
          {activityByDate.length ? (
            <Plot
              data={[
                {
                  x: activityByDate.map(([date]) => date),
                  y: activityByDate.map(([, value]) => value),
                  type: 'scatter',
                  mode: 'lines+markers',
                  line: { color: '#1a6b67', width: 3 },
                  marker: { color: '#be5b2d', size: 8 },
                },
              ]}
              layout={{
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                margin: { t: 10, r: 14, b: 48, l: 48 },
                xaxis: { title: { text: 'Simulation date' } },
                yaxis: { title: { text: 'Events' } },
              }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: '320px' }}
            />
          ) : (
            <div className="empty-state">No events match the current filter.</div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header d-flex justify-content-between align-items-center gap-3 flex-wrap">
          <span>Event log</span>
          <Form.Select style={{ maxWidth: 260 }} value={eventFilter} onChange={(event) => setEventFilter(event.target.value)}>
            <option value="all">All events</option>
            <option value="ORDER_CREATED">Order created</option>
            <option value="ORDER_RELEASED">Order released</option>
            <option value="ORDER_COMPLETED">Order completed</option>
            <option value="PO_CREATED">PO created</option>
            <option value="PO_DELIVERED">PO delivered</option>
            <option value="MATERIAL_CONSUMED">Material consumed</option>
            <option value="DAY_ADVANCED">Day advanced</option>
          </Form.Select>
        </div>
        <div className="card-body p-0">
          {filteredEvents.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Simulation Date</th>
                  <th>Timestamp</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.slice(0, 120).map((event) => (
                  <tr key={event.id}>
                    <td><span className="badge badge-neutral">{event.event_type}</span></td>
                    <td>{event.sim_date}</td>
                    <td>{new Date(event.timestamp).toLocaleString()}</td>
                    <td><div className="event-details">{event.details ? JSON.stringify(event.details, null, 2) : 'No details'}</div></td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">No events recorded for this filter yet.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Reports;
