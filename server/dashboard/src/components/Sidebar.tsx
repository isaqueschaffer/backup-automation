import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import {
  LayoutDashboard, Users, Archive, Settings, LogOut, Server
} from "lucide-react";
import pkg from "../../package.json";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Visão Geral" },
  { to: "/clients", icon: Users, label: "Clientes" },
  { to: "/backups", icon: Archive, label: "Backups" },
  { to: "/settings", icon: Settings, label: "Configurações" },
];

export default function Sidebar() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => { logout(); navigate("/login"); };

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-mark">
          <div className="sidebar-logo-icon">
            <Server size={18} color="white" />
          </div>
          <div className="sidebar-logo-text">
            <span className="sidebar-logo-title">TRILAN</span>
            <span className="sidebar-logo-sub">BACKUPS <span style={{ fontSize: '9px', backgroundColor: 'var(--primary)', color: 'white', padding: '1px 4px', borderRadius: '4px', marginLeft: '4px', fontWeight: 'bold', verticalAlign: 'middle' }}>V{pkg.version}</span></span>
          </div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-section-label">Menu</div>
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <button className="sidebar-logout" onClick={handleLogout}>
          <LogOut size={16} />
          Sair
        </button>
      </div>
    </aside>
  );
}
