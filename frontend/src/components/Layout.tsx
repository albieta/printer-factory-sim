import React, { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Alert, Button } from 'react-bootstrap';
import {
  FaBars,
  FaBoxes,
  FaChartLine,
  FaChevronDown,
  FaClipboardList,
  FaCog,
  FaFileAlt,
  FaIndustry,
  FaPlayCircle,
  FaTimes,
  FaTruck,
} from 'react-icons/fa';
import { getErrorMessage, simulationAPI } from '../services/api';
import type { SimulationStatus } from '../types';
import { announceSimulationUpdate, onSimulationUpdate } from '../utils/simulationEvents';

interface LayoutProps {
  children: React.ReactNode;
}

const navItems = [
  { path: '/', icon: <FaChartLine />, label: 'Overview' },
  { path: '/orders', icon: <FaClipboardList />, label: 'Manufacturing Orders' },
  { path: '/inventory', icon: <FaBoxes />, label: 'Inventory' },
  { path: '/suppliers', icon: <FaTruck />, label: 'Procurement' },
  { path: '/production', icon: <FaIndustry />, label: 'Assembly' },
  { path: '/reports', icon: <FaFileAlt />, label: 'Analytics' },
  { path: '/settings', icon: <FaCog />, label: 'Configuration' },
];

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [advanceNotice, setAdvanceNotice] = useState<string | null>(null);
  const [advanceError, setAdvanceError] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const location = useLocation();

  const loadStatus = async () => {
    try {
      const response = await simulationAPI.getStatus();
      setStatus(response.data);
      setStatusError(null);
    } catch (error) {
      setStatusError(getErrorMessage(error, 'Unable to load the workflow summary.'));
    }
  };

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= 992) {
        setSidebarOpen(false);
      }
    };

    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    void loadStatus();
    const clear = onSimulationUpdate(() => {
      void loadStatus();
    });

    return clear;
  }, [location.pathname]);

  const handleAdvanceDay = async () => {
    try {
      setAdvancing(true);
      const result = await simulationAPI.advanceDay();
      setAdvanceNotice(
        `Simulation advanced to ${result.data.sim_date}. Created ${result.data.orders_created} new demand orders, completed ${result.data.orders_completed} manufacturing orders, and received ${result.data.purchase_orders_delivered} purchase orders.`
      );
      setAdvanceError(null);
      announceSimulationUpdate();
      await loadStatus();
    } catch (error) {
      setAdvanceError(getErrorMessage(error, 'Failed to advance the simulation by one day.'));
    } finally {
      setAdvancing(false);
    }
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <div>
            <div className="sidebar-kicker">Operations Console</div>
            <h1>Printer Factory</h1>
          </div>
          <button
            type="button"
            className="sidebar-toggle d-lg-none"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation"
          >
            <FaTimes />
          </button>
        </div>

        <div className="sidebar-copy">
          Guide demand from review to assembly, replenish materials before storage runs tight, and understand the impact of each operating decision.
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              onClick={() => setSidebarOpen(false)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      {sidebarOpen ? (
        <button
          type="button"
          className="sidebar-backdrop d-lg-none"
          aria-label="Close navigation overlay"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}

      <div className="main-shell">
        <header className="topbar">
          <button
            type="button"
            className="sidebar-toggle d-lg-none"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation"
          >
            <FaBars />
          </button>
          <div>
            <div className="topbar-eyebrow">3D Printer Production Simulator</div>
            <div className="topbar-title">Demand-to-delivery command center</div>
          </div>
          <div className="topbar-actions">
            {status ? (
              <div className="topbar-meta">
                <div className="topbar-meta-item">
                  <span>Simulation date</span>
                  <strong>{status.current_date}</strong>
                </div>
                <div className="topbar-meta-item">
                  <span>Warehouse free</span>
                  <strong>{status.available_capacity.toFixed(0)} units</strong>
                </div>
              </div>
            ) : null}
            <Button variant="primary" onClick={() => void handleAdvanceDay()} disabled={advancing}>
              <FaPlayCircle className="me-2" />
              {advancing ? 'Advancing...' : 'Advance Day'}
            </Button>
          </div>
        </header>

        <div className="topbar-messages">
          {advanceError ? <Alert variant="danger" dismissible onClose={() => setAdvanceError(null)}>{advanceError}</Alert> : null}
          {advanceNotice ? <Alert variant="success" dismissible onClose={() => setAdvanceNotice(null)}>{advanceNotice}</Alert> : null}
        </div>

        <details className="workflow-strip" aria-label="Operational workflow" open={workflowOpen} onToggle={(event) => setWorkflowOpen((event.target as HTMLDetailsElement).open)}>
          <summary className="workflow-strip-summary">
            <div>
              <div className="section-kicker">Operational Flow</div>
              <h2>Follow work from demand to delivery</h2>
            </div>
            <div className="workflow-summary-meta">
              <span className="workflow-note">{statusError ?? 'Each stage shows the live count owned by its screen.'}</span>
              <FaChevronDown className="workflow-summary-icon" />
            </div>
          </summary>
          <div className="workflow-grid">
            {status?.workflow_stages?.map((stage) => {
              const active = location.pathname === stage.route || (stage.route === '/' && location.pathname === '/');
              return (
                <NavLink key={stage.key} to={stage.route} className={`workflow-stage ${active ? 'active' : ''}`}>
                  <span className="workflow-stage-owner">{navItems.find((item) => item.path === stage.route)?.label ?? 'Overview'}</span>
                  <strong>{stage.label}</strong>
                  <span className="workflow-stage-value">{stage.value}</span>
                  <p>{stage.description}</p>
                </NavLink>
              );
            })}
          </div>
        </details>

        <main className="main-content">{children}</main>
      </div>
    </div>
  );
};

export default Layout;
