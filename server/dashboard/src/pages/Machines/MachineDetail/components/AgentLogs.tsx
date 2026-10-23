import { useState } from "react";
import { ChevronDown, ChevronRight, CloudLightning } from "lucide-react";
import { AgentLog } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import { fmtDate } from "../../../../utils/date";

interface AgentLogsProps {
  logs: AgentLog[];
  mostrarPings: boolean;
  onTogglePings: (v: boolean) => void;
  lastSeen: string | null;
  online?: boolean;
}

const TIPO_LABELS: Record<string, string> = {
  ping: "Ping",
  ping_recovery: "Reconectou",
  queue_backup: "Fila",
  queue_backup_skipped: "Fila ignorada",
  email_sent: "E-mail enviado",
  email_error: "Erro de e-mail",
};

function tipoStyle(tipo: string): { background: string; color: string } {
  if (tipo === "ping" || tipo === "email_sent") {
    return { background: "rgba(16, 185, 129, 0.15)", color: "#10b981" };
  }
  if (tipo === "email_error") {
    return { background: "rgba(239, 68, 68, 0.15)", color: "#ef4444" };
  }
  return { background: "rgba(59, 130, 246, 0.15)", color: "#3b82f6" };
}

export default function AgentLogs({
  logs,
  mostrarPings,
  onTogglePings,
  lastSeen,
  online,
}: AgentLogsProps) {
  const [aberta, setAberta] = useState(false);

  return (
    <div style={{ marginTop: 20 }}>
      <button
        type="button"
        aria-expanded={aberta}
        onClick={() => setAberta((v) => !v)}
        style={{
          width: "100%",
          background: "none",
          border: "none",
          padding: 0,
          margin: 0,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 8,
          textAlign: "left",
          color: "inherit",
          font: "inherit",
        }}
      >
        {aberta ? (
          <ChevronDown size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
        ) : (
          <ChevronRight size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
        )}
        <CloudLightning size={15} style={{ flexShrink: 0, color: "var(--primary)" }} />
        <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>
          Eventos do Agente
        </span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: 999,
            background: "rgba(255,255,255,0.06)",
            color: "var(--text-muted)",
          }}
        >
          {logs.length} eventos
        </span>

        <div
          style={{
            marginLeft: "auto",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          {online !== undefined && (
            <StatusBadge status={online ? "ONLINE" : "OFFLINE"} />
          )}
          <span className="text-xs text-muted">
            {lastSeen ? `Último ping: ${fmtDate(lastSeen)}` : "Sem ping ainda"}
          </span>
        </div>
      </button>

      {aberta && (
        <div style={{ marginTop: 12 }}>
          <div style={{ marginBottom: 10 }}>
            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                cursor: "pointer",
                userSelect: "none",
                color: "var(--text-secondary)",
              }}
            >
              <input
                type="checkbox"
                checked={mostrarPings}
                onChange={(e) => onTogglePings(e.target.checked)}
                style={{ cursor: "pointer" }}
              />
              Mostrar pings
            </label>
          </div>

          {logs.length === 0 ? (
            <div className="empty-state" style={{ padding: 24 }}>
              {mostrarPings
                ? "Nenhum evento registrado ainda. O agente deve enviar pings a cada 15 segundos."
                : "Nenhuma instrução ou erro recente. Marque “Mostrar pings” para ver os pings."}
            </div>
          ) : (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                maxHeight: 300,
                overflowY: "auto",
                paddingRight: 6,
              }}
            >
              {logs.map((log) => {
                const label = TIPO_LABELS[log.event_type] || log.event_type;
                const colors = tipoStyle(log.event_type);
                return (
                  <div
                    key={log.id}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "130px auto 1fr",
                      alignItems: "center",
                      gap: 12,
                      background: "var(--surface-2, rgba(255,255,255,0.02))",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)",
                      padding: "6px 12px",
                      fontSize: 12,
                    }}
                  >
                    <div style={{ fontWeight: 600, color: "var(--text-muted)" }}>
                      {fmtDate(log.created_at)}
                    </div>
                    <div>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          textTransform: "uppercase",
                          padding: "2px 6px",
                          borderRadius: 4,
                          display: "inline-block",
                          whiteSpace: "nowrap",
                          background: colors.background,
                          color: colors.color,
                        }}
                      >
                        {label}
                      </span>
                    </div>
                    <div style={{ color: "var(--text-primary)", wordBreak: "break-word" }}>
                      {log.message}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
