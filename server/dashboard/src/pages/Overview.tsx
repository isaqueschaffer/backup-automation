import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchStats, fetchMachines } from "../api/client";
import { Stats, Machine } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { fmtDate, fmtSchedule } from "../utils/date";
import { Users, Server, CheckCircle, AlertCircle, Archive, Clock, Building2 } from "lucide-react";

export default function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loadError, setLoadError] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    let cancelled = false;
    fetchStats()
      .then((s) => { if (!cancelled) setStats(s); })
      .catch(() => { if (!cancelled) toast("Erro ao carregar estatísticas.", "error"); });
    fetchMachines()
      .then((m) => { if (!cancelled) setMachines(m); })
      .catch(() => { if (!cancelled) { setLoadError(true); toast("Erro ao carregar máquinas.", "error"); } });
    return () => { cancelled = true; };
  }, [toast]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Visão Geral</h1>
          <p className="page-subtitle">Status em tempo real de todas as máquinas</p>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-secondary" onClick={() => navigate("/clientes")}>
            <Users size={15} /> Clientes
          </button>
          <button className="btn btn-primary" onClick={() => navigate("/maquinas")}>
            <Server size={15} /> Máquinas
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card purple" style={{ cursor: "pointer" }} onClick={() => navigate("/clientes")}>
          <div className="stat-label">Clientes</div>
          <div className="stat-value purple">{stats?.customers_total ?? "—"}</div>
          <Users size={28} className="stat-icon" color="var(--accent)" />
        </div>
        <div className="stat-card cyan" style={{ cursor: "pointer" }} onClick={() => navigate("/maquinas")}>
          <div className="stat-label">Máquinas ativas / total</div>
          <div className="stat-value cyan">
            {stats ? `${stats.machines_active}/${stats.machines_total}` : "—"}
          </div>
          <CheckCircle size={28} className="stat-icon" color="var(--cyan)" />
        </div>
        <div className="stat-card green">
          <div className="stat-label">Backups OK Hoje</div>
          <div className="stat-value green">{stats?.backups_ok ?? "—"}</div>
          <Archive size={28} className="stat-icon" color="var(--ok)" />
        </div>
        <div className="stat-card red">
          <div className="stat-label">Erros Hoje</div>
          <div className="stat-value red">{stats?.backups_error ?? "—"}</div>
          <AlertCircle size={28} className="stat-icon" color="var(--err)" />
        </div>
      </div>

      {/* Cards das máquinas */}
      <div className="section-title"><Server size={15} />Máquinas</div>
      {machines.length === 0 && loadError ? (
        <div className="empty-state">
          <div>Não foi possível carregar as máquinas.</div>
        </div>
      ) : machines.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🖥️</div>
          <div>Nenhuma máquina cadastrada ainda.</div>
          <button className="btn btn-primary mt-2" onClick={() => navigate("/maquinas")}>
            Cadastrar primeira máquina
          </button>
        </div>
      ) : (
        <div className="clients-grid">
          {machines.map((m) => (
            <div key={m.id} className="client-card" onClick={() => navigate(`/maquinas/${m.id}`)}>
              <div className="client-card-header">
                <div className="flex gap-3 items-center">
                  <div className="client-avatar">
                    {m.name.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div className="client-name">{m.name}</div>
                    <div className="client-meta flex items-center gap-2">
                      <Clock size={11} />
                      {fmtSchedule(m.backup_hour, m.backup_minute)}
                      <Building2 size={11} />
                      {m.customer_name || "Sem cliente"}
                    </div>
                  </div>
                </div>
                <StatusBadge status={m.last_backup_status} />
              </div>
              <div className="client-stats">
                <div className="client-stat-item">
                  <div className="client-stat-label">Equipamentos</div>
                  <div className="client-stat-value">{m.nvr_count}</div>
                </div>
                <div className="client-stat-item">
                  <div className="client-stat-label">Último backup</div>
                  <div className="client-stat-value" style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {fmtDate(m.last_backup_at, { short: true, empty: "Nunca" })}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
