import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  FaBars,
  FaBoxes,
  FaChartLine,
  FaClipboardList,
  FaCog,
  FaFileAlt,
  FaIndustry,
  FaTimes,
  FaTruck,
} from 'react-icons/fa';

interface LayoutProps {
  children: React.ReactNode;
}

const navItems = [
  { path: '/', icon: <FaChartLine />, label: 'Overview' },
  { path: '/orders', icon: <FaClipboardList />, label: 'Orders' },
  { path: '/inventory', icon: <FaBoxes />, label: 'Inventory' },
  { path: '/suppliers', icon: <FaTruck />, label: 'Suppliers' },
  { path: '/production', icon: <FaIndustry />, label: 'Production' },
  { path: '/reports', icon: <FaFileAlt />, label: 'Reports' },
  { path: '/settings', icon: <FaCog />, label: 'Setup' },
];

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= 992) {
        setSidebarOpen(false);
      }
    };

    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

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
          Track demand, move materials, and tune throughput from one control room.
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
            <div className="topbar-title">Factory command center</div>
          </div>
        </header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
};

export default Layout;
