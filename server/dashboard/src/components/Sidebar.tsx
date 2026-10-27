import { useState, useEffect } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth, useRotulos, useSuperAdmin } from "../contexts/AuthContext";
import { fetchContas } from "../api/contas";
import type { Conta } from "../api/types";
import {
  LayoutDashboard,
  Users,
  Archive,
  Settings,
  LogOut,
  Server,
  UserCircle,
  Building2,
} from "lucide-react";
import pkg from "../../package.json";

function getPapelLabel(papel: string): string {
  switch (papel) {
    case "SUPER_ADMIN":
      return "Administrador da plataforma";
    case "ADMIN":
      return "Administrador";
    case "LEITURA":
      return "Somente leitura";
    default:
      return papel;
  }
}

export default function Sidebar() {
  const { me, logout, contaSelecionadaId, escolherConta } = useAuth();
  const { plural } = useRotulos();
  const isSuperAdmin = useSuperAdmin();
  const navigate = useNavigate();

  const [contas, setContas] = useState<Conta[]>([]);

  useEffect(() => {
    if (!isSuperAdmin) return;
    fetchContas()
      .then(setContas)
      .catch(() => setContas([]));
  }, [isSuperAdmin]);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const navItems = [
    { to: "/", icon: LayoutDashboard, label: "Visão Geral" },
    { to: "/clientes", icon: Users, label: plural },
    { to: "/maquinas", icon: Server, label: "Máquinas" },
    { to: "/backups", icon: Archive, label: "Backups" },
    { to: "/minha-conta", icon: UserCircle, label: "Minha conta" },
  ];

  const plataformaItems = [
    { to: "/contas", icon: Building2, label: "Contas" },
    { to: "/settings", icon: Settings, label: "Configurações" },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-mark">
          <div className="sidebar-logo-icon">
            <Server size={18} color="white" style={{ flexShrink: 0 }} />
          </div>
          <div className="sidebar-logo-text">
            <span className="sidebar-logo-title">TRILAN</span>
            <span className="sidebar-logo-sub">
              BACKUPS{" "}
              <span
                style={{
                  fontSize: "9px",
                  backgroundColor: "var(--primary)",
                  color: "white",
                  padding: "1px 4px",
                  borderRadius: "4px",
                  marginLeft: "4px",
                  fontWeight: "bold",
                  verticalAlign: "middle",
                }}
              >
                V{pkg.version}
              </span>
            </span>
          </div>
        </div>
      </div>

      {isSuperAdmin && (
        <div style={{ padding: "12px 12px 0" }}>
          <select
            className="form-input"
            style={{ width: "100%" }}
            aria-label="Conta"
            title="Conta em visualização"
            value={contaSelecionadaId ?? ""}
            onChange={(e) => escolherConta(e.target.value || null)}
          >
            <option value="">Todas as contas</option>
            {contas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
                {c.bloqueada ? " (bloqueada)" : ""}
              </option>
            ))}
          </select>
        </div>
      )}

      <nav className="sidebar-nav">
        <div className="sidebar-section-label">Menu</div>
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <Icon size={16} style={{ flexShrink: 0 }} />
            {label}
          </NavLink>
        ))}

        {isSuperAdmin && (
          <>
            <div className="sidebar-section-label">Plataforma</div>
            {plataformaItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              >
                <Icon size={16} style={{ flexShrink: 0 }} />
                {label}
              </NavLink>
            ))}
          </>
        )}
      </nav>

      <div className="sidebar-footer">
        {me && (
          <div style={{ marginBottom: 8, padding: "0 12px" }}>
            <div
              style={{
                fontSize: 13,
                color: "var(--text-primary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={me.usuario.nome}
            >
              {me.usuario.nome}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
              {getPapelLabel(me.usuario.papel)}
            </div>
          </div>
        )}
        <button className="sidebar-logout" onClick={handleLogout}>
          <LogOut size={16} style={{ flexShrink: 0 }} />
          Sair
        </button>
      </div>
    </aside>
  );
}
