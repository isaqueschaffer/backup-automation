import { useState } from "react";
import { Link } from "react-router-dom";
import { Archive, Download } from "lucide-react";
import { downloadBackupZip } from "../../../../api/client";
import { Backup } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import { useToast } from "../../../../components/Toast";
import { fmtDate } from "../../../../utils/date";
import { extractBlobError, saveBlob } from "../../../../utils/download";

// Últimos backups individuais das máquinas do cliente (um ZIP por máquina)
export default function CustomerBackups({ backups }: { backups: Backup[] | null }) {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const { toast } = useToast();

  const handleDownload = async (b: Backup) => {
    setDownloadingId(b.id);
    try {
      const data = await downloadBackupZip(b.id);
      saveBlob(data, b.zip_filename || "backup.zip");
    } catch (err) {
      toast(await extractBlobError(err), "error");
    } finally { setDownloadingId(null); }
  };

  return (
    <div style={{ marginBottom: 24 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="section-title" style={{ marginBottom: 0 }}><Archive size={15} /> Backups por máquina</div>
        <Link to="/backups" className="text-sm">Ver todos</Link>
      </div>
      {backups === null ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : backups.length === 0 ? (
        <div className="empty-state" style={{ padding: 32 }}>Nenhum backup registrado ainda.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Máquina</th><th>Data/Hora</th><th>Status</th><th>Origem</th><th>ZIP</th></tr>
            </thead>
            <tbody>
              {backups.map(b => (
                <tr key={b.id}>
                  <td style={{ fontWeight: 600 }}>
                    {b.machine_id
                      ? <Link to={`/maquinas/${b.machine_id}`} style={{ color: "var(--text-primary)" }}>{b.machine_name || "—"}</Link>
                      : (b.machine_name || "—")}
                  </td>
                  <td className="text-sm text-secondary">{fmtDate(b.started_at)}</td>
                  <td><StatusBadge status={b.status} /></td>
                  <td className="text-sm text-secondary">{b.trigger}</td>
                  <td>
                    {b.zip_filename ? (
                      <button className="btn-icon" title="Baixar ZIP" disabled={downloadingId === b.id} onClick={() => handleDownload(b)}>
                        {downloadingId === b.id ? <span className="spinner spinner-sm" /> : <Download size={14} />}
                      </button>
                    ) : <span className="text-muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
