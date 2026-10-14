import { Archive, ChevronRight } from "lucide-react";
import { Backup } from "../../../api/types";
import StatusBadge from "../../../components/StatusBadge";
import { fmtDate } from "../../../utils/date";

export default function BackupHistory({ backups }: { backups: Backup[] }) {
  return (
    <div>
      <div className="section-title">
        <Archive size={15} /> Histórico de Backups
        <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
          últimos 10
        </span>
      </div>
      {backups.length === 0 ? (
        <div className="empty-state" style={{ padding: "32px" }}>
          <div className="empty-icon">📦</div>
          <div>Nenhum backup realizado ainda.</div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {backups.map(b => (
            <div key={b.id} style={{
              display: "grid", gridTemplateColumns: "1fr auto auto auto auto",
              alignItems: "center", gap: 16,
              background: "var(--surface-2, rgba(255,255,255,0.02))",
              border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
              padding: "12px 20px"
            }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>
                  {fmtDate(b.started_at)}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  via {b.trigger}
                </div>
              </div>
              <StatusBadge status={b.status} />
              <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>
                {b.zip_size ? `${(b.zip_size / 1024 / 1024).toFixed(1)} MB` : "—"}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }} title="E-mail enviado">
                {b.email_sent ? "✅ E-mail" : "—"}
              </div>
              <ChevronRight size={14} style={{ color: "var(--text-muted)", opacity: 0.4 }} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
