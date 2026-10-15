import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import { fetchBackups, fetchMachines, fetchCustomers, resendBackupEmail, downloadBackupZip, downloadCustomerRunZip, downloadCustomerZip, BackupQuery } from "../api/client";
import { Backup, Customer, Machine, PaginatedBackups } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { fmtDate, localDateStr } from "../utils/date";
import { extractBlobError, saveBlob } from "../utils/download";
import { Download, Search, Calendar } from "lucide-react";

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
  const [machines, setMachines] = useState<Machine[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();
  const loadSeq = useRef(0);
  const [page, setPage] = useState(1);
  const [customerFilter, setCustomerFilter] = useState("");
  const [machineFilter, setMachineFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  
  const today = localDateStr();
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(today);
  
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [resendingEmailId, setResendingEmailId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    const params: BackupQuery = { page, size: 20 };
    if (customerFilter) params.customer_id = customerFilter;
    if (machineFilter) params.machine_id = machineFilter;
    if (statusFilter) params.status = statusFilter;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    try {
      const d = await fetchBackups(params);
      if (seq !== loadSeq.current) return; // resposta atrasada de um filtro anterior
      setData(d);
    } catch {
      if (seq !== loadSeq.current) return;
      toast("Erro ao carregar backups.", "error");
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [page, customerFilter, machineFilter, statusFilter, dateFrom, dateTo, toast]);

  useEffect(() => {
    fetchMachines().then(setMachines).catch(() => toast("Erro ao carregar máquinas.", "error"));
    fetchCustomers().then(setCustomers).catch(() => toast("Erro ao carregar clientes.", "error"));
  }, [toast]);

  // No filtro de máquina, só as máquinas do cliente escolhido
  const machineOptions = useMemo(
    () => customerFilter ? machines.filter(m => m.customer_id === customerFilter) : machines,
    [machines, customerFilter],
  );
  useEffect(() => { load(); }, [load]);
  // Invalida respostas pendentes ao desmontar
  useEffect(() => () => { loadSeq.current++; }, []);

  const handleDownload = async (b: Backup) => {
    try {
      setDownloadingId(b.id);
      if (b.customer_id) {
        if (b.run_id) {
          const safeName = (b.customer_name || "cliente").replace(/\s+/g, "_");
          const dateStr = b.started_at ? fmtDate(b.started_at).split(" ")[0].replace(/\//g, "-") : "backup";
          await downloadCustomerRunZip(b.customer_id, b.run_id, `cliente_${safeName}_${dateStr}.zip`);
        } else {
          const data = await downloadBackupZip(b.id, { direct_machine: false });
          saveBlob(data, `cliente_${(b.customer_name || "cliente").replace(/\s+/g, "_")}_${b.zip_filename || "backup.zip"}`);
        }
      } else {
        // Máquina sem cliente: baixa o ZIP individual da máquina (senha da máquina)
        const data = await downloadBackupZip(b.id, { direct_machine: true });
        saveBlob(data, b.zip_filename || "backup.zip");
      }
    } catch (err: unknown) {
      console.error("Erro ao baixar o backup:", err);
      const msg = await extractBlobError(err);
      toast(msg, "error");
    } finally {
      setDownloadingId(null);
    }
  };

  const handleResendEmail = async (backupId: string) => {
    try {
      setResendingEmailId(backupId);
      await resendBackupEmail(backupId);
      toast("E-mail reenviado com sucesso!", "success");
      load();
    } catch (err: unknown) {
      console.error("Erro ao reenviar e-mail:", err);
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      toast(axiosErr?.response?.data?.detail || "Falha ao reenviar e-mail. Verifique as configurações de SMTP.", "error");
    } finally {
      setResendingEmailId(null);
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Backups</h1>
          <p className="page-subtitle">Histórico completo de backups • Downloads priorizam o ZIP consolidado por cliente (senha do cliente)</p>
        </div>
      </div>

      {/* Filters */}
      <div className="filters-bar" style={{ flexWrap: "wrap" }}>
        <select className="form-input" value={customerFilter} title="Filtrar por cliente"
          onChange={e => { setCustomerFilter(e.target.value); setMachineFilter(""); setPage(1); }}>
          <option value="">Todos os clientes</option>
          {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="form-input" value={machineFilter} title="Filtrar por máquina"
          onChange={e => { setMachineFilter(e.target.value); setPage(1); }}>
          <option value="">Todas as máquinas</option>
          {machineOptions.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <select className="form-input" value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }}>
          <option value="">Todos os status</option>
          <option value="OK">OK</option>
          <option value="PARTIAL">Parcial</option>
          <option value="ERROR">Erro</option>
        </select>
        <div className="flex align-items-center gap-2" style={{ background: 'var(--surface)', padding: '0 10px', borderRadius: '4px', border: '1px solid var(--border)' }}>
          <Calendar size={14} className="text-muted" />
          <span className="text-sm font-medium">Início:</span>
          <input 
            type="date" 
            style={{ border: 'none', background: 'transparent', outline: 'none', padding: '8px 0', color: 'var(--text-color)' }}
            value={dateFrom} 
            onChange={e => { setDateFrom(e.target.value); setPage(1); }} 
            title="Data Inicial"
          />
        </div>
        <div className="flex align-items-center gap-2" style={{ background: 'var(--surface)', padding: '0 10px', borderRadius: '4px', border: '1px solid var(--border)' }}>
          <Calendar size={14} className="text-muted" />
          <span className="text-sm font-medium">Fim:</span>
          <input 
            type="date" 
            style={{ border: 'none', background: 'transparent', outline: 'none', padding: '8px 0', color: 'var(--text-color)' }}
            value={dateTo} 
            onChange={e => { setDateTo(e.target.value); setPage(1); }} 
            title="Data Final"
          />
        </div>
        <button className="btn btn-primary" onClick={() => load()} style={{ height: '36px', padding: '0 20px' }}>
          <Search size={16} style={{ marginRight: 6 }} /> Buscar
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
                  <th>Máquina</th>
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
                    <td>
                      {b.customer_id
                        ? <Link to={`/clientes/${b.customer_id}`}>{b.customer_name || "Cliente"}</Link>
                        : <span className="text-muted">—</span>}
                    </td>
                    <td style={{ fontWeight: 600 }}>
                      {b.machine_id
                        ? <Link to={`/maquinas/${b.machine_id}`} style={{ color: "var(--text-primary)" }}>{b.machine_name || "—"}</Link>
                        : (b.machine_name || "—")}
                    </td>
                    <td className="text-sm text-secondary">{fmtDate(b.started_at)}</td>
                    <td><StatusBadge status={b.status} /></td>
                    <td className="text-secondary text-sm" style={{ verticalAlign: 'top', minWidth: '220px' }}>
                      <EquipamentosCell results={b.nvr_results} />
                    </td>
                    <td className="text-secondary text-sm">{fmtSize(b.zip_size)}</td>
                    <td>
                      {b.email_sent ? (
                        <span title="E-mail enviado com sucesso">✅</span>
                      ) : (
                        <button
                          className="btn btn-secondary btn-sm"
                          style={{ padding: "2px 6px", fontSize: 11, display: "inline-flex", alignItems: "center", gap: 4 }}
                          onClick={() => handleResendEmail(b.id)}
                          disabled={resendingEmailId === b.id}
                          title="Tentar reenviar e-mail de relatório"
                        >
                          {resendingEmailId === b.id ? (
                            <span className="spinner spinner-sm" style={{ width: 10, height: 10, borderWidth: 2 }} />
                          ) : (
                            "✉️ Reenviar"
                          )}
                        </button>
                      )}
                    </td>
                    <td className="text-secondary text-sm">{b.trigger}</td>
                    <td>
                      {(b.zip_filename || b.customer_id) && (
                        <button
                          onClick={() => handleDownload(b)}
                          className="btn-icon"
                          title={
                            b.customer_id
                              ? `Baixar ZIP do cliente "${b.customer_name || "Cliente"}" (prioridade de cliente com senha no ZIP externo)`
                              : "Baixar ZIP da máquina (protegido com a senha da máquina)"
                          }
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
