import React, { useEffect, useMemo, useState } from 'react';
import Plot from 'react-plotly.js';
import { Alert, Button } from 'react-bootstrap';
import { FaCalendarAlt, FaPlayCircle } from 'react-icons/fa';
import { eventsAPI, getErrorMessage, inventoryAPI, simulationAPI } from '../services/api';
import type { CapacityInfo, Event, SimulationStatus } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Overview: React.FC = () => {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [capacity, setCapacity] = useState<CapacityInfo | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [advancing, setAdvancing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = async () => {
    try {
      setLoading(true);
      const [statusRes, capacityRes, eventsRes] = await Promise.all([
        simulationAPI.getStatus(),
        inventoryAPI.getCapacity(),
        eventsAPI.getEvents({ limit: 150 }),
      ]);
      setStatus(statusRes.data);
      setCapacity(capacityRes.data);
      setEvents(eventsRes.data);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load the overview dashboard.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOverview();
  }, []);

  const handleAdvanceDay = async () => {
    try {
      setAdvancing(true);
      const result = await simulationAPI.advanceDay();
      setNotice(
        `Simulation advanced to ${result.data.sim_date}. Created ${result.data.orders_created} orders, completed ${result.data.orders_completed}, and delivered ${result.data.purchase_orders_delivered} purchase orders.`
      );
      await loadOverview();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to advance the simulation by one day.'));
    } finally {
      setAdvancing(false);
    }
  };

  const eventsByDate = useMemo(() => {
    const counts = new Map<string, number>();
    [...events].reverse().forEach((event) => {
      counts.set(event.sim_date, (counts.get(event.sim_date) ?? 0) + 1);
    });
    return Array.from(counts.entries()).map(([date, value]) => ({ date, value }));
  }, [events]);

  const eventMix = useMemo(() => {
    const counts = new Map<string, number>();
    events.forEach((event) => {
      counts.set(event.event_type, (counts.get(event.event_type) ?? 0) + 1);
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);
  }, [events]);

  if (loading) {
    return <LoadingSpinner label="Loading operations overview..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Overview</div>
          <h1>Factory pulse</h1>
          <p>Advance the simulation, watch warehouse pressure, and keep an eye on demand and throughput from one place.</p>
        </div>
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {notice ? <Alert variant="success">{notice}</Alert> : null}

      <div className="hero-panel">
        <div className="section-title">
          <div>
            <div className="section-kicker">Simulation control</div>
            <h3>Run the next operating day</h3>
          </div>
          <Button variant="primary" size="lg" onClick={handleAdvanceDay} disabled={advancing}>
            <FaPlayCircle className="me-2" />
            {advancing ? 'Advancing day...' : 'Advance Day'}
          </Button>
        </div>
        <p className="text-muted mb-0">
          Every advance processes deliveries, generates fresh demand, executes production, and writes a new event trail for analytics.
        </p>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card info">
          <div className="kpi-label">Simulation Date</div>
          <div className="kpi-value"><FaCalendarAlt /></div>
          <div className="kpi-subtext">{status?.current_date ?? 'Unknown'}</div>
        </div>
        <div className="kpi-card warning">
          <div className="kpi-label">Pending Orders</div>
          <div className="kpi-value">{status?.pending_orders ?? 0}</div>
          <div className="kpi-subtext">Demand waiting to be released</div>
        </div>
        <div className="kpi-card success">
          <div className="kpi-label">Completed Orders</div>
          <div className="kpi-value">{status?.completed_orders ?? 0}</div>
          <div className="kpi-subtext">Finished units shipped through production</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Warehouse Use</div>
          <div className="kpi-value">{capacity ? `${capacity.usage_percentage.toFixed(0)}%` : '0%'}</div>
          <div className="kpi-subtext">{capacity ? `${capacity.current_usage.toFixed(0)} / ${capacity.warehouse_capacity}` : 'No capacity data'}</div>
        </div>
      </div>

      <div className="data-grid">
        <div className="chart-container">
          <div className="section-title">
            <h4>Event volume by day</h4>
          </div>
          {eventsByDate.length ? (
            <Plot
              data={[
                {
                  x: eventsByDate.map((item) => item.date),
                  y: eventsByDate.map((item) => item.value),
                  type: 'bar',
                  marker: { color: '#be5b2d' },
                },
              ]}
              layout={{
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                margin: { t: 12, r: 12, b: 50, l: 48 },
                xaxis: { title: { text: 'Simulation date' } },
                yaxis: { title: { text: 'Events' } },
              }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: '320px' }}
            />
          ) : (
            <div className="empty-state">Advance the simulation to generate activity history.</div>
          )}
        </div>

        <div className="chart-container">
          <div className="section-title">
            <h4>Recent event mix</h4>
          </div>
          {eventMix.length ? (
            <Plot
              data={[
                {
                  type: 'pie',
                  labels: eventMix.map(([label]) => label),
                  values: eventMix.map(([, value]) => value),
                  hole: 0.58,
                  marker: { colors: ['#be5b2d', '#1a6b67', '#d18a1a', '#b6463b', '#2f7d4a', '#7c6250'] },
                  textinfo: 'label+percent',
                },
              ]}
              layout={{
                paper_bgcolor: 'transparent',
                margin: { t: 12, r: 12, b: 12, l: 12 },
                showlegend: false,
              }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: '320px' }}
            />
          ) : (
            <div className="empty-state">Event categories will appear here once the simulator is running.</div>
          )}
        </div>
      </div>

      <div className="two-column">
        <div className="surface-panel card-body">
          <div className="section-title">
            <h4>Operational snapshot</h4>
          </div>
          <div className="metric-list">
            <div className="metric-item stat-row">
              <span>Total logged events</span>
              <strong>{status?.total_events ?? 0}</strong>
            </div>
            <div className="metric-item stat-row">
              <span>Tracked inventory SKUs</span>
              <strong>{status?.inventory_items ?? 0}</strong>
            </div>
            <div className="metric-item stat-row">
              <span>Available warehouse capacity</span>
              <strong>{capacity ? capacity.available_capacity.toFixed(2) : '0.00'}</strong>
            </div>
            <div className="metric-item">
              <div className="stat-row">
                <span>Warehouse saturation</span>
                <strong>{capacity ? `${capacity.usage_percentage.toFixed(1)}%` : '0%'}</strong>
              </div>
              <div className="progress-shell mt-2">
                <div className="progress-fill" style={{ width: `${Math.min(capacity?.usage_percentage ?? 0, 100)}%` }} />
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">Recent event stream</div>
          <div className="card-body">
            {events.length ? (
              <div className="list-stack">
                {events.slice(0, 6).map((event) => (
                  <div className="metric-item" key={event.id}>
                    <div className="inline-meta mb-2">
                      <span className="badge badge-neutral">{event.event_type}</span>
                      <span className="text-muted mono">{event.sim_date}</span>
                    </div>
                    <div className="event-details">{event.details ? JSON.stringify(event.details, null, 2) : 'No details provided.'}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">No events recorded yet.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Overview;
