import React, { useEffect, useMemo, useState } from 'react';
import { Alert } from 'react-bootstrap';
import { FaCalendarAlt } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import ResponsivePlot from '../components/ResponsivePlot';
import { eventsAPI, getErrorMessage, simulationAPI } from '../services/api';
import type { Event, SimulationStatus } from '../types';
import { describeEventDetails, formatEventType, formatNumber } from '../utils/formatters';
import LoadingSpinner from '../components/LoadingSpinner';
import { onSimulationUpdate } from '../utils/simulationEvents';

const Overview: React.FC = () => {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
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
    const clear = onSimulationUpdate(() => {
      void loadOverview();
    });

    return clear;
  }, []);

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
        controls="This is the cross-functional status view. Use it to spot today’s main bottleneck before deciding whether to review demand, expedite materials, or change factory settings."
        next="The global Advance Day control in the top bar processes deliveries, new demand, production completions, and event logging for every downstream screen."
        tip="The most useful overview signals are current-state ones: queue health, blocked work, space pressure, and shared assembly capacity."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}

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
        <div className="kpi-card danger">
          <div className="kpi-label">Rejected Demand</div>
          <div className="kpi-value">{status?.rejected_orders ?? 0}</div>
          <div className="kpi-subtext">Orders declined during planner review</div>
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
                x: ['Awaiting release', 'Queued', 'Blocked', 'Completed', 'Rejected'],
                y: [
                  status?.pending_orders ?? 0,
                  status?.released_orders ?? 0,
                  status?.blocked_orders ?? 0,
                  status?.completed_orders ?? 0,
                  status?.rejected_orders ?? 0,
                ],
                type: 'bar',
                marker: { color: ['#d18a1a', '#1a6b67', '#b6463b', '#2f7d4a', '#705649'] },
              },
            ]}
            layout={{
              title: { text: 'Manufacturing order status snapshot' },
              xaxis: { title: { text: 'Current state' } },
              yaxis: { title: { text: 'Orders' } },
              margin: { t: 68, r: 24, b: 56, l: 56 },
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
