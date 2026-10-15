import { ArrowLeft, Clock, CloudLightning, Download, Edit2, RotateCcw, Trash2 } from "lucide-react";
import { Customer } from "../../../../api/types";
import { fmtDate, fmtSchedule } from "../../../../utils/date";
import HealthBadge, { QueueBadge } from "../../components/HealthBadge";

export type CustomerAction = "backup" | "stop" | "zip" | "edit" | "delete";

// Cabeçalho do cliente: nome, resumo e ações principais
export default function CustomerHeader({ customer, busy, onBack, onAction }: {
  customer: Customer;
  busy: CustomerAction | null;
  onBack: () => void;
  onAction: (a: CustomerAction) => void;
}) {
  const c = customer;
  return (
    <>
      <div className="page-header">
        <div className="flex items-center gap-3">
          <button className="btn-icon" onClick={onBack} title="Voltar para Clientes">
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="page-title" style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              {c.name} <HealthBadge health={c.health} /> {c.queue_active && <QueueBadge />}
            </h1>
            {c.description && <p className="page-subtitle">{c.description}</p>}
          </div>
        </div>
        <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
          {c.queue_active ? (
            <button className="btn btn-secondary" disabled={busy === "stop"} onClick={() => onAction("stop")}
              style={{ color: "var(--err)", borderColor: "rgba(239,68,68,0.4)" }} title="Parar / destravar a fila em andamento">
              {busy === "stop" ? <span className="spinner spinner-sm" /> : <RotateCcw size={15} />} Parar fila
            </button>
          ) : (
            <button className="btn btn-secondary" disabled={busy === "backup" || c.machines_total === 0} onClick={() => onAction("backup")}
              title="Faz o backup de todas as máquinas, uma por vez, na ordem da fila">
              {busy === "backup" ? <span className="spinner spinner-sm" /> : <CloudLightning size={15} />} Backup em fila
            </button>
          )}
          <button className="btn btn-secondary" disabled={busy === "zip"} onClick={() => onAction("zip")}
            title="Baixar um ZIP com o último backup de cada máquina">
            {busy === "zip" ? <span className="spinner spinner-sm" /> : <Download size={15} />} Baixar ZIP
          </button>
          <button className="btn btn-secondary" onClick={() => onAction("edit")}>
            <Edit2 size={15} /> Editar cliente
          </button>
          <button className="btn btn-secondary" style={{ color: "var(--err)" }} onClick={() => onAction("delete")}>
            <Trash2 size={15} /> Excluir
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: "14px 20px", marginBottom: 24, display: "flex", gap: 32, flexWrap: "wrap", fontSize: 13 }}>
        <div>
          <div className="text-xs text-muted">Horário diário</div>
          <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
            <Clock size={13} /> {fmtSchedule(c.backup_hour, c.backup_minute)}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted">Máquinas online</div>
          <div style={{ fontWeight: 600, color: c.machines_total === 0 ? "var(--text-muted)" : c.machines_online > 0 ? "var(--ok)" : "var(--err)" }}>
            {c.machines_online}/{c.machines_total}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted">Último backup</div>
          <div style={{ fontWeight: 600 }}>{fmtDate(c.last_backup_at, { empty: "Nunca" })}</div>
        </div>
      </div>
    </>
  );
}
