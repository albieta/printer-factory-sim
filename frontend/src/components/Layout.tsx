import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { 
  FaChartLine, 
  FaClipboardList, 
  FaBoxes, 
  FaTruck, 
  FaIndustry, 
  FaFileAlt, 
  FaCog,
  FaBars,
  FaTimes
} from 'react-icons/fa';

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const navItems = [
    { path: '/', icon: <FaChartLine />, label: 'Overview' },
    { path: '/orders', icon: <FaClipboardList />, label: 'Orders' },
    { path: '/inventory', icon: <FaBoxes />, label: 'Inventory' },
    { path: '/suppliers', icon: <FaTruck />, label: 'Suppliers' },
    { path: '/production', icon: <FaIndustry />, label: 'Production' },
    { path: '/reports', icon: <FaFileAlt />, label: 'Reports' },
    { path: '/settings', icon: <FaCog />, label: 'Settings' },
  ];

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : 'collapsed'}`}>
        <div className="sidebar-header">
          <h2>🏭 Printer Factory Sim</h2>
          <button 
            className="btn btn-sm btn-link text-white d-lg-none"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            {sidebarOpen ? <FaTimes /> : <FaBars />}
          </button>
        </div>
        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <div className="nav-item" key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                onClick={() => setSidebarOpen(true)}
              >
                {item.icon}
                <span>{item.label}</span>
              </NavLink>
            </div>
          ))}
        </nav>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        {children}
      </main>
    </div>
  );
};

export default Layout;
