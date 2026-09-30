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

function getStatusColor(status: string) {
  switch (status.toUpperCase()) {
    case 'OK': return { bg: '#337a54', text: '#ffffff', icon: '🟢' }; 
    case 'PARCIAL': 
    case 'PARTIAL': return { bg: '#d97706', text: '#ffffff', icon: '🟡' }; 
    case 'ERROR':
    case 'ERRO': return { bg: '#9f1239', text: '#ffffff', icon: '🔴' }; 
    case 'SEM_ARQUIVOS':
    case 'BACKUP_ANTIGO': return { bg: '#9a3412', text: '#ffffff', icon: '🟡' }; 
    default: return { bg: '#5A5A5A', text: '#ffffff', icon: '⚪' }; 
  }
}

function EquipamentosCell({ results }: { results: any[] | null }) {
  const [showDetails, setShowDetails] = useState(false);
  
  if (!results || results.length === 0) return <span>—</span>;

  const grouped: Record<string, { ok: number; error: number; old: number; partial: number; total: number, items: any[] }> = {};
  
  results.forEach(r => {
    let tipo = r.tipo?.toUpperCase();
    if (!tipo) {
      if (r.nome.toUpperCase().includes('HUAWEI')) tipo = 'HUAWEI';
      else if (r.nome.toUpperCase().includes('MIKROTIK')) tipo = 'MIKROTIK';
      else if (r.nome.toUpperCase().includes('UNM')) tipo = 'UNM2000';
      else if (r.nome.toUpperCase().includes('PABX')) tipo = 'PABX';
      else tipo = 'NVR'; 
    }
    
    if (!grouped[tipo]) grouped[tipo] = { ok: 0, error: 0, old: 0, partial: 0, total: 0, items: [] };
    
    grouped[tipo].items.push(r);
    grouped[tipo].total++;
    
    const s = r.status.toUpperCase();
    if (s === 'OK' || s === 'SEM_ARQUIVOS') grouped[tipo].ok++;
    else if (s === 'ERRO' || s === 'ERROR') grouped[tipo].error++;
    else if (s === 'PARCIAL' || s === 'PARTIAL') grouped[tipo].partial++;
    else if (s === 'BACKUP_ANTIGO') grouped[tipo].old++;
    else grouped[tipo].error++;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        {Object.entries(grouped).map(([tipo, stats]) => {
          let catStatus = 'OK';
          if (stats.error === stats.total) catStatus = 'ERRO';
          else if (stats.error > 0 || stats.partial > 0) catStatus = 'PARCIAL';
          else if (stats.old > 0) catStatus = 'BACKUP_ANTIGO';
          
          const color = getStatusColor(catStatus);
          
          return (
            <span key={tipo} style={{ 
              display: 'inline-flex', alignItems: 'center', gap: '4px',
              backgroundColor: color.bg, color: color.text, 
              padding: '2px 6px', borderRadius: '4px', fontSize: '11px', fontWeight: 500,
              boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.1)'
            }}>
              {tipo}: {catStatus.replace('_', ' ')}
            </span>
          );
        })}
      </div>
      
      <button 
        onClick={() => setShowDetails(true)}
        style={{ 
          background: 'none', border: 'none', color: 'var(--brand-primary)', 
          fontSize: '11px', cursor: 'pointer', textAlign: 'left', padding: 0,
          textDecoration: 'underline'
        }}
      >
        Detalhes
      </button>

      {showDetails && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.7)', zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }} onClick={() => setShowDetails(false)}>
          <div style={{
            backgroundColor: 'var(--bg-elevated, #131324)', 
            padding: '24px', borderRadius: '12px', 
            maxWidth: '500px', width: '90%', maxHeight: '80vh', overflowY: 'auto',
            boxShadow: 'var(--shadow-lg, 0 10px 30px rgba(0,0,0,0.5))',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)'
          }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>Status dos Equipamentos</h3>
              <button onClick={() => setShowDetails(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: 'var(--text-secondary)' }}>✖</button>
            </div>
            
            {Object.entries(grouped).map(([tipo, stats]) => (
              <div key={tipo} style={{ marginBottom: '16px' }}>
                <strong style={{ display: 'block', marginBottom: '8px', paddingBottom: '4px', borderBottom: '1px solid var(--border)' }}>{tipo}</strong>
                {stats.items.map((item, idx) => {
                  const color = getStatusColor(item.status);
                  return (
                    <div key={idx} style={{ padding: '6px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px dashed var(--border)' }}>
                      <span style={{ color: 'var(--text-secondary)', fontSize: '13px', paddingRight: '12px' }}>{item.nome}</span>
                      <span style={{ 
                        backgroundColor: color.bg, color: color.text, 
                        padding: '2px 6px', borderRadius: '4px', fontSize: '11px', fontWeight: 500,
                        whiteSpace: 'nowrap', boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.05)'
                      }}>
                        {item.status.replace('_', ' ')}
                      </span>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
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
                    <td className="text-secondary text-sm" style={{ verticalAlign: 'top', minWidth: '220px' }}>
                      <EquipamentosCell results={b.nvr_results} />
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
