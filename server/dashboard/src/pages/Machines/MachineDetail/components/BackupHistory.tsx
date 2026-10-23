import { useState } from "react";
import { Archive, Download } from "lucide-react";
import { Backup } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import { fmtDate } from "../../../../utils/date";
import { downloadBackupZip } from "../../../../api/client";
import { extractBlobError, saveBlob } from "../../../../utils/download";
import { useToast } from "../../../../components/Toast";

export default function BackupHistory({ backups }: { backups: Backup[] }) {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const { toast } = useToast();

  const handleDownload = async (backupId: string, filename: string) => {
    try {
      setDownloadingId(backupId);
      // Download direto na máquina: usa a senha da máquina!
      const data = await downloadBackupZip(backupId, { direct_machine: true });
      saveBlob(data, filename || "backup.zip");
    } catch (err: unknown) {
      console.error("Erro ao baixar o backup da máquina:", err);
      const msg = await extractBlobError(err);
      toast(msg, "error");
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div>
      <div className="section-title">
        <Archive size={15} style={{ flexShrink: 0 }} /> Histórico de Backups da Máquina
        <span
          style={{
            marginLeft: 8,
            fontSize: 12,
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: 999,
            background: "rgba(255,255,255,0.06)",
            color: "var(--text-muted)",
          }}
        >
          últimos 10
        </span>
      </div>

      {backups.length === 0 ? (
        <div className="empty-state" style={{ padding: "32px" }}>
          <div className="empty-icon">📦</div>
          <div>Nenhum backup realizado ainda.</div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {backups.map((b, index) => (
            <div
              key={b.id}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr auto auto auto auto",
                alignItems: "center",
                gap: 16,
                background: "var(--surface-2, rgba(255,255,255,0.02))",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "6px 14px",
                fontSize: 12,
              }}
            >
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>
                  {fmtDate(b.started_at)}
                  {index === 0 && (
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        textTransform: "uppercase",
                        color: "var(--primary)",
                        border: "1px solid var(--primary)",
                        borderRadius: 4,
                        padding: "1px 5px",
                        marginLeft: 8,
                      }}
                    >
                      último
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
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
              <div>
                {b.zip_filename ? (
                  <button
                    type="button"
                    onClick={() => handleDownload(b.id, b.zip_filename!)}
                    className="btn-icon"
                    title="Baixar ZIP desta máquina (protegido com a senha da máquina)"
                    disabled={downloadingId === b.id}
                  >
                    {downloadingId === b.id ? (
                      <span className="spinner spinner-sm" style={{ width: 14, height: 14, borderWidth: 2 }} />
                    ) : (
                      <Download size={14} style={{ flexShrink: 0 }} />
                    )}
                  </button>
                ) : (
                  <span className="text-muted" style={{ fontSize: 12 }}>—</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
