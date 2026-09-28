import { useEffect, useState, useCallback } from "react";
import { fetchBackups, fetchClients } from "../api/client";
import api from "../api/client";
import { Backup, Client, PaginatedBackups } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import { Download, Search } from "lucide-react";

// Função auxiliar para formatar erros de blob
async function extractBlobError(err: unknown): Promise<string> {
  let msg = "Erro ao baixar o arquivo.";
  try {
    const axiosErr = err as { response?: { data?: Blob } };
    if (axiosErr?.response?.data instanceof Blob) {
      const text = await axiosErr.response.data.text();
      const json = JSON.parse(text);
      if (json?.detail) msg = json.detail;
    }
  } catch { /* ignora */ }
  return msg;
}

function fmtDate(s: string | null) {
  if (!s) return "—";
  const str = s.endsWith("Z") ? s : s + "Z";
  return new Date(str).toLocaleString("pt-BR");
}

function fmtSize(n: number | null) {
  if (!n) return "—";
  if (n > 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024).toFixed(0)} KB`;
}

export default function Backups() {
  const [data, setData] = useState<PaginatedBackups | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [clientFilter, setClientFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const params: Record<string, unknown> = { page, size: 20 };
    if (clientFilter) params.client_id = clientFilter;
    if (statusFilter) params.status = statusFilter;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    const d = await fetchBackups(params);
    setData(d);
    setLoading(false);
  }, [page, clientFilter, statusFilter, dateFrom, dateTo]);

  useEffect(() => { fetchClients().then(setClients); }, []);
  useEffect(() => { load(); }, [load]);

  const handleDownload = async (backupId: string, filename: string) => {
    try {
      setDownloadingId(backupId);
      const res = await api.get(`/backups/${backupId}/download`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/zip" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || "backup.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      console.error("Erro ao baixar o backup:", err);
      const msg = await extractBlobError(err);
      alert(msg);
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Backups</h1>
          <p className="page-subtitle">Histórico completo de todos os backups</p>
        </div>
      </div>

      {/* Filters */}
      <div className="filters-bar" style={{ flexWrap: "wrap" }}>
        <select className="form-input" value={clientFilter} onChange={e => { setClientFilter(e.target.value); setPage(1); }}>
          <option value="">Todos os clientes</option>
          {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="form-input" value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }}>
          <option value="">Todos os status</option>
          <option value="OK">OK</option>
          <option value="PARTIAL">Parcial</option>
          <option value="ERROR">Erro</option>
        </select>
        <input 
          type="date" 
          className="form-input" 
          value={dateFrom} 
          onChange={e => { setDateFrom(e.target.value); setPage(1); }} 
          title="Data Inicial"
        />
        <input 
          type="date" 
          className="form-input" 
          value={dateTo} 
          onChange={e => { setDateTo(e.target.value); setPage(1); }} 
          title="Data Final"
        />
        <button className="btn btn-secondary" onClick={() => load()}>
          <Search size={14} /> Atualizar
        </button>
      </div>

      {loading ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : !data || data.items.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📦</div>
          <div>Nenhum backup encontrado.</div>
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th>Data/Hora</th>
                  <th>Status</th>
                  <th>Equipamentos</th>
                  <th>ZIP</th>
                  <th>Email</th>
                  <th>Origem</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((b: Backup) => (
                  <tr key={b.id}>
                    <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{b.client_name}</td>
                    <td className="text-sm text-secondary">{fmtDate(b.started_at)}</td>
                    <td><StatusBadge status={b.status} /></td>
                    <td className="text-secondary text-sm">
                      {b.nvr_results
                        ? b.nvr_results.map((r) => `${r.nome}: ${r.status}`).join(", ")
                        : "—"}
                    </td>
                    <td className="text-secondary text-sm">{fmtSize(b.zip_size)}</td>
                    <td>{b.email_sent ? "✅" : "—"}</td>
                    <td className="text-secondary text-sm">{b.trigger}</td>
                    <td>
                      {b.zip_filename && (
                        <button
                          onClick={() => handleDownload(b.id, b.zip_filename!)}
                          className="btn-icon"
                          title="Baixar ZIP"
                          disabled={downloadingId === b.id}
                        >
                          {downloadingId === b.id ? (
                            <span className="spinner spinner-sm" style={{ width: 14, height: 14, borderWidth: 2 }} />
                          ) : (
                            <Download size={14} />
                          )}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="pagination">
            <button className="page-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>‹</button>
            {Array.from({ length: data.pages }, (_, i) => i + 1)
              .filter(p => Math.abs(p - page) <= 2)
              .map(p => (
                <button key={p} className={`page-btn ${p === page ? "active" : ""}`} onClick={() => setPage(p)}>{p}</button>
              ))}
            <button className="page-btn" disabled={page === data.pages} onClick={() => setPage(p => p + 1)}>›</button>
          </div>
        </>
      )}
    </>
  );
}
