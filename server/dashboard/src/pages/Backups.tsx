import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import { fetchBackups, fetchMachines, fetchCustomers, resendBackupEmail, downloadBackupZip, BackupQuery } from "../api/client";
import { Backup, Customer, Machine, NVRResult, PaginatedBackups } from "../api/types";
import Modal from "../components/Modal";
import StatusBadge from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { fmtDate, localDateStr } from "../utils/date";
import { extractBlobError, saveBlob } from "../utils/download";
import { isStatusProblem, statusTone } from "../utils/statusTone";
import { Check, Download, Mail, Search } from "lucide-react";
import { useRotulos } from "../contexts/AuthContext";

function fmtSize(n: number | null) {
  if (!n) return "—";
  if (n > 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024).toFixed(0)} KB`;
}

function triggerLabel(trigger: string): string {
  switch (trigger) {
    case "scheduled": return "Agendado";
    case "queue": return "Fila";
    case "manual_machine": return "Avulso";
    case "manual":
    case "manual_dashboard": return "Manual";
    default: return trigger;
  }
}

function EquipamentosCell({ results }: { results: NVRResult[] | null }) {
  const [showDetails, setShowDetails] = useState(false);

  if (!results || results.length === 0) return <span>—</span>;

  const grouped: Record<string, { ok: number; error: number; old: number; partial: number; total: number; items: NVRResult[] }> = {};

  results.forEach(r => {
    let tipo = r.tipo?.toUpperCase();
    if (!tipo) {
      if (r.nome.toUpperCase().includes("HUAWEI")) tipo = "HUAWEI";
      else if (r.nome.toUpperCase().includes("MIKROTIK")) tipo = "MIKROTIK";
      else if (r.nome.toUpperCase().includes("UNM")) tipo = "UNM2000";
      else if (r.nome.toUpperCase().includes("PABX")) tipo = "PABX";
      else tipo = "NVR";
    }

    if (!grouped[tipo]) grouped[tipo] = { ok: 0, error: 0, old: 0, partial: 0, total: 0, items: [] };

    grouped[tipo].items.push(r);
    grouped[tipo].total++;

    const s = r.status.toUpperCase();
    if (s === "OK" || s === "SEM_ARQUIVOS") grouped[tipo].ok++;
    else if (s === "ERRO" || s === "ERROR") grouped[tipo].error++;
    else if (s === "PARCIAL" || s === "PARTIAL") grouped[tipo].partial++;
    else if (s === "BACKUP_ANTIGO") grouped[tipo].old++;
    else grouped[tipo].error++;
  });

  return (
    <>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {Object.entries(grouped).map(([tipo, stats]) => {
          let catStatus = "OK";
          if (stats.error === stats.total) catStatus = "ERRO";
          else if (stats.error > 0 || stats.partial > 0) catStatus = "PARCIAL";
          else if (stats.old > 0) catStatus = "BACKUP_ANTIGO";

          const tom = catStatus === "OK" ? "ok" : catStatus === "ERRO" ? "err" : "warn";

          return (
            <button
              key={tipo}
              type="button"
              className={`badge ${tom}`}
              onClick={() => setShowDetails(true)}
              title="Ver detalhes dos equipamentos"
              style={{ cursor: "pointer", border: "none" }}
            >
              <span className={`dot ${tom}`} />
              {tipo} {stats.ok}/{stats.total}
            </button>
          );
        })}
      </div>

      {showDetails && (
        <Modal title="Status dos equipamentos" onClose={() => setShowDetails(false)} width={520}>
          {Object.entries(grouped).map(([tipo, stats]) => (
            <div key={tipo} style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, fontSize: 13, paddingBottom: 4, borderBottom: "1px solid var(--border)", marginBottom: 6 }}>
                {tipo}
              </div>
              {stats.items.map((item, idx) => (
                <div key={idx} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, padding: "6px 0" }}>
                  <span className="text-sm text-secondary">{item.nome}</span>
                  <StatusBadge status={item.status} />
                </div>
              ))}
            </div>
          ))}
        </Modal>
      )}
    </>
  );
}

export default function Backups() {
  const { singular, pluralMin, singularMin } = useRotulos();
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
    fetchCustomers().then(setCustomers).catch(() => toast(`Erro ao carregar ${pluralMin}.`, "error"));
  }, [pluralMin, toast]);

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
      // Baixa o backup individual da máquina (protegido exclusivamente com a senha da máquina)
      const data = await downloadBackupZip(b.id, { direct_machine: true });
      const safeMachine = (b.machine_name || "maquina").replace(/\s+/g, "_");
      let filename = b.zip_filename || `backup_${safeMachine}.zip`;
      if (!filename.toLowerCase().includes(safeMachine.toLowerCase())) {
        filename = filename.startsWith("backup_")
          ? `backup_${safeMachine}_${filename.slice(7)}`
          : `backup_${safeMachine}_${filename}`;
      }
      saveBlob(data, filename);
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
          <p className="page-subtitle">Histórico de backups por máquina. O download é o ZIP da própria máquina (senha da máquina).</p>
        </div>
      </div>

      {/* Filters */}
      <div className="filters-bar" style={{ flexWrap: "wrap" }}>
        <select
          className="form-input"
          value={customerFilter}
          title={`Filtrar por ${singularMin}`}
          onChange={e => { setCustomerFilter(e.target.value); setMachineFilter(""); setPage(1); }}
        >
          <option value="">Todos os {pluralMin}</option>
          {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select
          className="form-input"
          value={machineFilter}
          title="Filtrar por máquina"
          onChange={e => { setMachineFilter(e.target.value); setPage(1); }}
        >
          <option value="">Todas as máquinas</option>
          {machineOptions.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <select
          className="form-input"
          value={statusFilter}
          title="Filtrar por status"
          onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
        >
          <option value="">Todos os status</option>
          <option value="OK">OK</option>
          <option value="PARTIAL">Parcial</option>
          <option value="ERROR">Erro</option>
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="text-xs text-muted">Início</span>
          <input
            type="date"
            className="form-input"
            style={{ width: 150 }}
            value={dateFrom}
            onChange={e => { setDateFrom(e.target.value); setPage(1); }}
            title="Data inicial"
          />
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="text-xs text-muted">Fim</span>
          <input
            type="date"
            className="form-input"
            style={{ width: 150 }}
            value={dateTo}
            onChange={e => { setDateTo(e.target.value); setPage(1); }}
            title="Data final"
          />
        </label>
        <button className="btn btn-primary" onClick={() => load()}>
          <Search size={14} style={{ flexShrink: 0 }} /> Buscar
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
          <div className="text-sm text-muted" style={{ marginBottom: 10 }}>
            {data.total} backup(s) · página {data.page} de {data.pages}
          </div>
          <div className="table-wrap" style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Máquina</th>
                  <th>Data/Hora</th>
                  <th>Status</th>
                  <th>Equipamentos</th>
                  <th>Tamanho</th>
                  <th>E-mail</th>
                  <th>Baixar</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((b: Backup) => {
                  const tone = statusTone(b.status);
                  const acento = tone === "err" ? "var(--err)" : isStatusProblem(b.status) ? "var(--warn)" : "transparent";

                  return (
                    <tr key={b.id}>
                      <td style={{ boxShadow: `inset 3px 0 0 ${acento}` }}>
                        <div style={{ fontWeight: 600 }}>
                          {b.machine_id ? (
                            <Link to={`/maquinas/${b.machine_id}`} style={{ color: "var(--text-primary)" }}>
                              {b.machine_name || "—"}
                            </Link>
                          ) : (
                            b.machine_name || "—"
                          )}
                        </div>
                        <div className="text-xs text-muted" style={{ marginTop: 2 }}>
                          {b.customer_id ? (
                            <Link to={`/clientes/${b.customer_id}`}>
                              {b.customer_name || singular}
                            </Link>
                          ) : (
                            `Sem ${singularMin}`
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="text-sm">{fmtDate(b.started_at)}</div>
                        <div className="text-xs text-muted" style={{ marginTop: 2 }}>{triggerLabel(b.trigger)}</div>
                      </td>
                      <td>
                        <StatusBadge status={b.status} />
                      </td>
                      <td style={{ verticalAlign: "middle", minWidth: 200 }}>
                        <EquipamentosCell results={b.nvr_results} />
                      </td>
                      <td className="text-sm text-secondary" style={{ whiteSpace: "nowrap" }}>
                        {fmtSize(b.zip_size)}
                      </td>
                      <td>
                        {b.email_sent ? (
                          <span title="E-mail enviado" style={{ color: "var(--ok)", display: "inline-flex" }}>
                            <Check size={16} style={{ flexShrink: 0 }} />
                          </span>
                        ) : (
                          <button
                            className="btn-icon"
                            title="Reenviar e-mail de relatório"
                            disabled={resendingEmailId === b.id}
                            onClick={() => handleResendEmail(b.id)}
                          >
                            {resendingEmailId === b.id ? (
                              <span className="spinner spinner-sm" />
                            ) : (
                              <Mail size={14} style={{ flexShrink: 0 }} />
                            )}
                          </button>
                        )}
                      </td>
                      <td>
                        {b.zip_filename && (
                          <button
                            onClick={() => handleDownload(b)}
                            className="btn-icon"
                            title="Baixar ZIP da máquina (protegido com a senha da máquina)"
                            disabled={downloadingId === b.id}
                          >
                            {downloadingId === b.id ? (
                              <span className="spinner spinner-sm" />
                            ) : (
                              <Download size={14} style={{ flexShrink: 0 }} />
                            )}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
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
