import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Form, Table } from 'react-bootstrap';
import { FaDownload } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import ResponsivePlot from '../components/ResponsivePlot';
import { eventsAPI, exportAPI, getErrorMessage } from '../services/api';
import type { Event } from '../types';
import { describeEventDetails, formatEventType, formatTimestamp } from '../utils/formatters';
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
      const label = formatEventType(event.event_type);
      counts.set(label, (counts.get(label) ?? 0) + 1);
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
    return <LoadingSpinner label="Loading analytics and exports..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Analytics</div>
          <h1>Explain what happened across the flow</h1>
          <p>Use analytics to understand how demand moved, where bottlenecks appeared, and which operating decisions changed inventory, procurement, and assembly outcomes over time.</p>
        </div>
      </div>

      <PageGuide
        title="Analytics"
        controls="This screen summarizes the event history recorded by the simulator and gives you exports for comparing scenarios outside the app."
        next="The event log helps explain why the workflow strip changed, which orders moved, and whether inventory or warehouse capacity caused procurement or manufacturing issues."
        tip="Use filtered events when you want to focus on one subsystem, such as only order releases or only purchase-order receipts."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="action-bar">
        <div>
          <div className="section-kicker">Data exports</div>
          <h3 className="mb-1">Download scenario snapshots</h3>
          <p className="text-muted mb-0">Export the full simulator state or just the inventory and event history for deeper analysis.</p>
        </div>
        <div className="action-buttons">
          <Button variant="primary" onClick={() => void handleExport('full')}><FaDownload className="me-2" />Full state</Button>
          <Button variant="success" onClick={() => void handleExport('inventory')}><FaDownload className="me-2" />Inventory</Button>
          <Button variant="warning" onClick={() => void handleExport('events')}><FaDownload className="me-2" />Events</Button>
        </div>
      </div>

      <div className="data-grid">
        <div className="chart-container">
          <ResponsivePlot
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
            layout={{ title: { text: 'Event distribution' }, showlegend: false, margin: { t: 68, r: 20, b: 20, l: 20 } }}
            minHeight={340}
          />
        </div>

        <div className="chart-container">
          <ResponsivePlot
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
              title: { text: 'Activity over time' },
              xaxis: { title: { text: 'Simulation date' } },
              yaxis: { title: { text: 'Events logged' } },
              margin: { t: 68, r: 24, b: 56, l: 56 },
            }}
            minHeight={340}
          />
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
            <option value="ORDER_BLOCKED_MATERIALS">Order blocked by materials</option>
            <option value="PO_CREATED">Purchase order created</option>
            <option value="PO_DELIVERED">Purchase order delivered</option>
            <option value="PO_REJECTED_CAPACITY">Purchase order rejected</option>
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
                  <th>Recorded At</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.slice(0, 120).map((event) => (
                  <tr key={event.id}>
                    <td><span className="badge badge-neutral">{formatEventType(event.event_type)}</span></td>
                    <td>{event.sim_date}</td>
                    <td>{formatTimestamp(event.timestamp)}</td>
                    <td><div className="event-summary">{describeEventDetails(event.details)}</div></td>
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
