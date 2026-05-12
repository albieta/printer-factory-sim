import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Form, Table } from 'react-bootstrap';
import { FaDownload } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import ResponsivePlot from '../components/ResponsivePlot';
import { eventsAPI, exportAPI, getErrorMessage } from '../services/api';
import type { Event } from '../types';
import { describeEventDetails, formatEventType, formatTimestamp } from '../utils/formatters';
import LoadingSpinner from '../components/LoadingSpinner';
import { onSimulationUpdate } from '../utils/simulationEvents';

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
    const clear = onSimulationUpdate(() => {
      void loadEvents();
    });

    return clear;
  }, []);

  const filteredEvents = useMemo(
    () => events.filter((event) => eventFilter === 'all' || event.event_type === eventFilter),
    [eventFilter, events]
  );

  const manufacturingFlow = useMemo(() => {
    const daily = new Map<string, { created: number; released: number; completed: number }>();
    const ensure = (date: string) => {
      if (!daily.has(date)) {
        daily.set(date, { created: 0, released: 0, completed: 0 });
      }
      return daily.get(date)!;
    };

    events.forEach((event) => {
      const day = ensure(event.sim_date);
      if (event.event_type === 'ORDER_CREATED') {
        day.created += 1;
      }
      if (event.event_type === 'ORDER_RELEASED' || event.event_type === 'ORDER_UNBLOCKED_MATERIALS') {
        day.released += 1;
      }
      if (event.event_type === 'ORDER_COMPLETED') {
        day.completed += 1;
      }
    });

    return Array.from(daily.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [events]);

  const procurementFlow = useMemo(() => {
    const daily = new Map<string, { created: number; delivered: number; rejected: number }>();
    const ensure = (date: string) => {
      if (!daily.has(date)) {
        daily.set(date, { created: 0, delivered: 0, rejected: 0 });
      }
      return daily.get(date)!;
    };

    events.forEach((event) => {
      const day = ensure(event.sim_date);
      if (event.event_type === 'PO_CREATED') {
        day.created += 1;
      }
      if (event.event_type === 'PO_DELIVERED') {
        day.delivered += 1;
      }
      if (event.event_type === 'PO_REJECTED_CAPACITY') {
        day.rejected += 1;
      }
    });

    return Array.from(daily.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [events]);

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
        controls="This screen explains the simulation with a few focused charts instead of mixed event rollups. Manufacturing flow and procurement flow each get their own view."
        next="Use the event log when you need the detailed reason behind a status change, delivery, rejection, or shortage."
        tip="The charts intentionally stay subsystem-specific so planners can distinguish demand flow from procurement flow at a glance."
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
                x: manufacturingFlow.map(([date]) => date),
                y: manufacturingFlow.map(([, value]) => value.created),
                type: 'bar',
                name: 'Created',
                marker: { color: '#d18a1a' },
              },
              {
                x: manufacturingFlow.map(([date]) => date),
                y: manufacturingFlow.map(([, value]) => value.released),
                type: 'bar',
                name: 'Released or unblocked',
                marker: { color: '#1a6b67' },
              },
              {
                x: manufacturingFlow.map(([date]) => date),
                y: manufacturingFlow.map(([, value]) => value.completed),
                type: 'bar',
                name: 'Completed',
                marker: { color: '#2f7d4a' },
              },
            ]}
            layout={{
              barmode: 'group',
              title: { text: 'Daily manufacturing flow' },
              xaxis: { title: { text: 'Simulation date' } },
              yaxis: { title: { text: 'Orders' } },
              margin: { t: 68, r: 24, b: 56, l: 56 },
            }}
            minHeight={340}
          />
        </div>

        <div className="chart-container">
          <ResponsivePlot
            data={[
              {
                x: procurementFlow.map(([date]) => date),
                y: procurementFlow.map(([, value]) => value.created),
                type: 'bar',
                name: 'POs created',
                marker: { color: '#be5b2d' },
              },
              {
                x: procurementFlow.map(([date]) => date),
                y: procurementFlow.map(([, value]) => value.delivered),
                type: 'bar',
                name: 'Delivered',
                marker: { color: '#1a6b67' },
              },
              {
                x: procurementFlow.map(([date]) => date),
                y: procurementFlow.map(([, value]) => value.rejected),
                type: 'bar',
                name: 'Rejected',
                marker: { color: '#b6463b' },
              },
            ]}
            layout={{
              barmode: 'group',
              title: { text: 'Daily procurement flow' },
              xaxis: { title: { text: 'Simulation date' } },
              yaxis: { title: { text: 'Purchase orders' } },
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
            <option value="ORDER_UNBLOCKED_MATERIALS">Order unblocked</option>
            <option value="ORDER_REJECTED">Order rejected</option>
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
