import { CloudLightning } from "lucide-react";
import { AgentLog } from "../../../../api/types";
import { fmtDate } from "../../../../utils/date";

export default function AgentLogs({ logs }: { logs: AgentLog[] }) {
  return (
    <div style={{ marginTop: 20 }}>
      <div className="section-title">
        <CloudLightning size={15} /> Eventos do Agente (Pings e Instruções)
        <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
          últimos {logs.length}
        </span>
      </div>
      {logs.length === 0 ? (
        <div className="empty-state" style={{ padding: "32px" }}>
          <div className="empty-icon">📡</div>
          <div>Nenhum evento registrado ainda. O agente deve enviar pings a cada 15 segundos.</div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 300, overflowY: "auto", paddingRight: 8 }}>
          {logs.map(log => (
            <div key={log.id} style={{
              display: "grid", gridTemplateColumns: "140px auto 1fr",
              alignItems: "center", gap: 12,
              background: "var(--surface-2, rgba(255,255,255,0.02))",
              border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
              padding: "10px 16px"
            }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>
                {fmtDate(log.created_at)}
              </div>
              <div style={{
                fontSize: 10, fontWeight: 700, textTransform: "uppercase", padding: "2px 6px", borderRadius: 4,
                background: log.event_type === "ping" ? "rgba(16, 185, 129, 0.15)" : "rgba(59, 130, 246, 0.15)",
                color: log.event_type === "ping" ? "#10b981" : "#3b82f6"
              }}>
                {log.event_type}
              </div>
              <div style={{ fontSize: 13, color: "var(--text-primary)" }}>
                {log.message}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
