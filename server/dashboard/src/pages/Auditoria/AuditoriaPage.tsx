import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { AuditoriaQuery, fetchAuditoria, fetchCustomers, fetchMachines, fetchUsuariosAuditoria } from "../../api/client";
import { Customer, Machine, PaginatedAuditoria } from "../../api/types";
import { useToast } from "../../components/Toast";
import { useRotulos } from "../../contexts/AuthContext";
import { fmtDate } from "../../utils/date";

// Auditoria: quem alterou o quê no painel (equipamentos, câmeras, máquinas, comandos de alarme...).
// Os mesmos eventos aparecem em "Eventos do Agente" de cada máquina; aqui ficam juntos, com filtros.
export default function AuditoriaPage() {
  const { singular, pluralMin, singularMin } = useRotulos();
  const { toast } = useToast();
  const [data, setData] = useState<PaginatedAuditoria | null>(null);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [usuarios, setUsuarios] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const loadSeq = useRef(0);

  const [page, setPage] = useState(1);
  const [customerFilter, setCustomerFilter] = useState("");
  const [machineFilter, setMachineFilter] = useState("");
  const [usuarioFilter, setUsuarioFilter] = useState("");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    const params: AuditoriaQuery = { page, size: 30 };
    if (customerFilter) params.customer_id = customerFilter;
    if (machineFilter) params.machine_id = machineFilter;
    if (usuarioFilter) params.usuario = usuarioFilter;
    if (buscaAplicada.trim()) params.q = buscaAplicada.trim();
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    try {
      const d = await fetchAuditoria(params);
      if (seq !== loadSeq.current) return; // resposta atrasada de um filtro anterior
      setData(d);
    } catch {
      if (seq !== loadSeq.current) return;
      toast("Erro ao carregar a auditoria.", "error");
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [page, customerFilter, machineFilter, usuarioFilter, buscaAplicada, dateFrom, dateTo, toast]);

  useEffect(() => {
    fetchMachines().then(setMachines).catch(() => toast("Erro ao carregar máquinas.", "error"));
    fetchCustomers().then(setCustomers).catch(() => toast(`Erro ao carregar ${pluralMin}.`, "error"));
    fetchUsuariosAuditoria().then(setUsuarios).catch(() => setUsuarios([]));
  }, [pluralMin, toast]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => () => { loadSeq.current++; }, []);

  // No filtro de máquina, só as máquinas do cliente escolhido
  const machineOptions = useMemo(
    () => (customerFilter ? machines.filter(m => m.customer_id === customerFilter) : machines),
    [machines, customerFilter],
  );

  const aplicarBusca = () => {
    setPage(1);
    setBuscaAplicada(busca);
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Auditoria</h1>
          <p className="page-subtitle">
            Quem alterou o quê no painel, com o horário. Fica guardado por {data?.dias_retencao ?? 365} dias.
          </p>
        </div>
      </div>

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
          value={usuarioFilter}
          title="Filtrar por usuário"
          onChange={e => { setUsuarioFilter(e.target.value); setPage(1); }}
        >
          <option value="">Todos os usuários</option>
          {usuarios.map(u => <option key={u} value={u}>{u}</option>)}
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
        <input
          type="text"
          className="form-input"
          placeholder="Buscar no texto..."
          value={busca}
          maxLength={100}
          onChange={e => setBusca(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") aplicarBusca(); }}
          style={{ minWidth: 180, flex: 1 }}
        />
        <button className="btn btn-primary" onClick={aplicarBusca}>
          <Search size={14} style={{ flexShrink: 0 }} /> Buscar
        </button>
      </div>

      {loading ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : !data || data.items.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🕘</div>
          <div>Nenhuma alteração encontrada.</div>
        </div>
      ) : (
        <>
          <div className="text-sm text-muted" style={{ marginBottom: 10 }}>
            {data.total} alteração(ões) · página {data.page} de {data.pages}
          </div>
          <div className="table-wrap" style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th style={{ whiteSpace: "nowrap" }}>Data/Hora</th>
                  <th>Usuário</th>
                  <th>Máquina</th>
                  <th>O que mudou</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map(item => (
                  <tr key={item.id}>
                    <td className="text-sm" style={{ whiteSpace: "nowrap" }}>{fmtDate(item.created_at)}</td>
                    <td className="text-sm" style={{ fontWeight: 600 }}>{item.usuario}</td>
                    <td>
                      <div style={{ fontWeight: 600 }}>
                        <Link to={`/maquinas/${item.machine_id}`} style={{ color: "var(--text-primary)" }}>
                          {item.machine_name || "—"}
                        </Link>
                      </div>
                      <div className="text-xs text-muted" style={{ marginTop: 2 }}>
                        {item.customer_id ? (
                          <Link to={`/clientes/${item.customer_id}`}>{item.customer_name || singular}</Link>
                        ) : (
                          `Sem ${singularMin}`
                        )}
                      </div>
                    </td>
                    <td className="text-sm" style={{ wordBreak: "break-word" }}>
                      {/* A mensagem já começa com o usuário; a coluna dele mostra isso, então corta o prefixo */}
                      {item.message.startsWith(item.usuario + " ") ? item.message.slice(item.usuario.length + 1) : item.message}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

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
