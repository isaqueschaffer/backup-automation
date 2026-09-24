import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchStats, fetchClients } from "../api/client";
import { Stats, Client } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import { Users, CheckCircle, AlertCircle, Archive, Clock } from "lucide-react";

function fmtDate(s: string | null) {
  if (!s) return "Nunca";
  return new Date(s).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function fmtSchedule(h: number, m: number) {
  return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}`;
}

// Gatilho para build (Docploy)
export default function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    fetchStats().then(setStats);
    fetchClients().then(setClients);
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Visão Geral</h1>
          <p className="page-subtitle">Status em tempo real de todos os clientes</p>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-secondary" onClick={() => alert("Docploy deploy atualizado com sucesso!")}>
            Teste Docploy
          </button>
          <button className="btn btn-primary" onClick={() => navigate("/clients")}>
            <Users size={15} /> Gerenciar Clientes
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card purple">
          <div className="stat-label">Clientes Totais</div>
          <div className="stat-value purple">{stats?.total_clients ?? "—"}</div>
          <Users size={28} className="stat-icon" color="var(--accent)" />
        </div>
        <div className="stat-card cyan">
          <div className="stat-label">Ativos</div>
          <div className="stat-value cyan">{stats?.active_clients ?? "—"}</div>
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

      {/* Client cards */}
      <div className="section-title"><Users size={15} />Clientes</div>
      {clients.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🏢</div>
          <div>Nenhum cliente cadastrado ainda.</div>
          <button className="btn btn-primary mt-2" onClick={() => navigate("/clients")}>
            Cadastrar primeiro cliente
          </button>
        </div>
      ) : (
        <div className="clients-grid">
          {clients.map((c) => (
            <div key={c.id} className="client-card" onClick={() => navigate(`/clients/${c.id}`)}>
              <div className="client-card-header">
                <div className="flex gap-3 items-center">
                  <div className="client-avatar">
                    {c.name.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div className="client-name">{c.name}</div>
                    <div className="client-meta flex items-center gap-2">
                      <Clock size={11} />
                      {fmtSchedule(c.backup_hour, c.backup_minute)}
                    </div>
                  </div>
                </div>
                <StatusBadge status={c.last_backup_status} />
              </div>
              <div className="client-stats">
                <div className="client-stat-item">
                  <div className="client-stat-label">Equipamentos</div>
                  <div className="client-stat-value">{c.nvr_count}</div>
                </div>
                <div className="client-stat-item">
                  <div className="client-stat-label">Último backup</div>
                  <div className="client-stat-value" style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {fmtDate(c.last_backup_at)}
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
