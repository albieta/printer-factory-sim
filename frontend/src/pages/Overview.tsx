import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button } from 'react-bootstrap';
import { FaCalendarAlt, FaPlayCircle } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import ResponsivePlot from '../components/ResponsivePlot';
import { eventsAPI, getErrorMessage, simulationAPI } from '../services/api';
import type { Event, SimulationStatus } from '../types';
import { announceSimulationUpdate } from '../utils/simulationEvents';
import { describeEventDetails, formatEventType, formatNumber } from '../utils/formatters';
import LoadingSpinner from '../components/LoadingSpinner';

const Overview: React.FC = () => {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [advancing, setAdvancing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = async () => {
    try {
      setLoading(true);
      const [statusRes, eventsRes] = await Promise.all([
        simulationAPI.getStatus(),
        eventsAPI.getEvents({ limit: 150 }),
      ]);
      setStatus(statusRes.data);
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
        `Simulation advanced to ${result.data.sim_date}. Created ${result.data.orders_created} new demand orders, completed ${result.data.orders_completed} manufacturing orders, and received ${result.data.purchase_orders_delivered} purchase orders.`
      );
      announceSimulationUpdate();
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
      counts.set(formatEventType(event.event_type), (counts.get(formatEventType(event.event_type)) ?? 0) + 1);
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);
  }, [events]);

  const bottleneck = useMemo(() => {
    if (!status) {
      return 'Loading current constraints...';
    }

    if (status.available_capacity < status.warehouse_capacity * 0.1) {
      return 'Warehouse space is the main bottleneck. Procurement receipts are close to the storage limit.';
    }

    if (status.blocked_orders > 0) {
      return 'Material shortages are the main bottleneck. Blocked orders need stock before they can move back into assembly.';
    }

    if (status.released_orders > 0 && status.effective_daily_assembly_hours > 0) {
      return 'Assembly queue is active. Review released work and advance the simulation to consume today\'s shared capacity.';
    }

    return 'No immediate bottleneck detected. The system has free warehouse space and no blocked work right now.';
  }, [status]);

  if (loading) {
    return <LoadingSpinner label="Loading operations overview..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Overview</div>
          <h1>Daily operating cycle</h1>
          <p>Use this screen to move the simulation one day forward and see where the current bottleneck sits before you touch orders, procurement, or configuration.</p>
        </div>
      </div>

      <PageGuide
        title="Overview"
        controls="This is the simulation heartbeat. Advancing the day triggers deliveries, creates new demand, consumes shared assembly capacity, and records the resulting events."
        next="The daily results change every downstream screen: new manufacturing orders appear in review, warehouse levels change, and assembly or procurement pressure may increase."
        tip="If the workflow strip shows congestion building in one stage, advance the day only after you understand whether that stage is constrained by stock, space, or assembly hours."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {notice ? <Alert variant="success">{notice}</Alert> : null}

      <div className="hero-panel hero-panel-split">
        <div>
          <div className="section-kicker">Simulation control</div>
          <h3>Run the next operating day</h3>
          <p className="hero-copy">
            The simulator processes demand, receipts, material consumption, completions, and event logging in a daily batch. Nothing moves until you advance the day.
          </p>
        </div>
        <Button variant="primary" size="lg" onClick={handleAdvanceDay} disabled={advancing}>
          <FaPlayCircle className="me-2" />
          {advancing ? 'Advancing day...' : 'Advance Day'}
        </Button>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card info">
          <div className="kpi-label">Simulation Date</div>
          <div className="kpi-value"><FaCalendarAlt /></div>
          <div className="kpi-subtext">{status?.current_date ?? 'Unknown'}</div>
        </div>
        <div className="kpi-card warning">
          <div className="kpi-label">Demand Awaiting Review</div>
          <div className="kpi-value">{status?.pending_orders ?? 0}</div>
          <div className="kpi-subtext">Orders not yet released into assembly</div>
        </div>
        <div className="kpi-card success">
          <div className="kpi-label">Assembly Queue</div>
          <div className="kpi-value">{status?.released_orders ?? 0}</div>
          <div className="kpi-subtext">Released orders competing for daily capacity</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Warehouse Free Space</div>
          <div className="kpi-value">{status ? formatNumber(status.available_capacity) : '0'}</div>
          <div className="kpi-subtext">of {status ? formatNumber(status.warehouse_capacity) : '0'} total units</div>
        </div>
      </div>

      <div className="two-column">
        <div className="surface-panel card-body">
          <div className="section-title">
            <h4>Current bottleneck</h4>
          </div>
          <div className="metric-item emphasis-item">
            <p>{bottleneck}</p>
          </div>
          <div className="metric-list compact-list">
            <div className="metric-item stat-row">
              <span>Blocked by materials</span>
              <strong>{status?.blocked_orders ?? 0}</strong>
            </div>
            <div className="metric-item stat-row">
              <span>Purchase orders in transit</span>
              <strong>{status?.pending_purchase_orders ?? 0}</strong>
            </div>
            <div className="metric-item stat-row">
              <span>Delivered purchase orders</span>
              <strong>{status?.delivered_purchase_orders ?? 0}</strong>
            </div>
            <div className="metric-item stat-row">
              <span>Shared assembly hours per day</span>
              <strong>{formatNumber(status?.effective_daily_assembly_hours ?? 0, 1)}</strong>
            </div>
          </div>
        </div>

        <div className="surface-panel card-body">
          <div className="section-title">
            <h4>How the day flows</h4>
          </div>
          <div className="list-stack">
            {(status?.workflow_stages ?? []).map((stage, index) => (
              <div className="metric-item" key={stage.key}>
                <div className="stat-row">
                  <strong>{index + 1}. {stage.label}</strong>
                  <span className="badge badge-neutral">{stage.value}</span>
                </div>
                <div className="text-muted mt-2">{stage.description}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="data-grid">
        <div className="chart-container">
          <ResponsivePlot
            data={[
              {
                x: eventsByDate.map((item) => item.date),
                y: eventsByDate.map((item) => item.value),
                type: 'bar',
                marker: { color: '#be5b2d' },
              },
            ]}
            layout={{
              title: { text: 'Event volume by day' },
              xaxis: { title: { text: 'Simulation date' } },
              yaxis: { title: { text: 'Events logged' } },
              margin: { t: 68, r: 24, b: 56, l: 56 },
            }}
            minHeight={340}
          />
        </div>

        <div className="chart-container">
          <ResponsivePlot
            data={[
              {
                type: 'pie',
                labels: eventMix.map(([label]) => label),
                values: eventMix.map(([, value]) => value),
                hole: 0.55,
                marker: { colors: ['#be5b2d', '#1a6b67', '#d18a1a', '#b6463b', '#2f7d4a', '#7c6250'] },
                textinfo: 'label+percent',
              },
            ]}
            layout={{
              title: { text: 'Recent event mix' },
              showlegend: false,
              margin: { t: 68, r: 20, b: 20, l: 20 },
            }}
            minHeight={340}
          />
        </div>
      </div>

      <div className="card">
        <div className="card-header">Latest operating signals</div>
        <div className="card-body">
          {events.length ? (
            <div className="list-stack">
              {events.slice(0, 6).map((event) => (
                <div className="metric-item" key={event.id}>
                  <div className="inline-meta mb-2">
                    <span className="badge badge-neutral">{formatEventType(event.event_type)}</span>
                    <span className="text-muted mono">{event.sim_date}</span>
                  </div>
                  <div className="event-summary">{describeEventDetails(event.details)}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">Advance the simulation to generate activity history.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Overview;
