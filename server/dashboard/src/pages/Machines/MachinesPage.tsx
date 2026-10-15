import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchMachines, fetchCustomers, createMachine, deleteMachine, restartAgentAll, triggerBackupAll,
} from "../../api/client";
import { Customer, Machine } from "../../api/types";
import StatusBadge from "../../components/StatusBadge";
import { useToast } from "../../components/Toast";
import { fmtDate, fmtSchedule } from "../../utils/date";
import { apiErrorMessage } from "../../utils/errors";
import { Plus, Trash2, Eye, RotateCcw, Play } from "lucide-react";
import NewMachineModal, { NewMachineForm } from "./components/NewMachineModal";
import NewMachineKeyModal from "./components/NewMachineKeyModal";

const NO_CUSTOMER = "__none__";

export default function MachinesPage() {
  const [machines, setMachines] = useState<Machine[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [customerFilter, setCustomerFilter] = useState(""); // "" = todos
  const [showCreate, setShowCreate] = useState(false);
  const [newKey, setNewKey] = useState<{ id: string; name: string; api_key: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  const load = useCallback(() => {
    fetchMachines()
      .then((m) => { setMachines(m); setLoadFailed(false); })
      .catch(() => { setLoadFailed(true); toast("Erro ao carregar máquinas.", "error"); })
      .finally(() => setLoading(false));
    fetchCustomers().then(setCustomers).catch(() => { /* filtro fica só com "Todos"/"Sem cliente" */ });
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  const visible = useMemo(() => {
    if (!customerFilter) return machines;
    if (customerFilter === NO_CUSTOMER) return machines.filter(m => !m.customer_id);
    return machines.filter(m => m.customer_id === customerFilter);
  }, [machines, customerFilter]);

  const handleCreate = async (form: NewMachineForm) => {
    if (!form.name.trim()) { toast("Nome obrigatório.", "error"); return; }
    const customer = customers.find(c => c.id === form.customer_id);
    setSaving(true);
    try {
      const data = await createMachine({
        name: form.name.trim(),
        backup_hour: customer ? customer.backup_hour : form.backup_hour,
        backup_minute: customer ? customer.backup_minute : form.backup_minute,
        email_to: form.email_to.split(",").map(e => e.trim()).filter(Boolean),
        zip_password: form.zip_password || undefined,
        active: true,
        ...(customer ? { customer_id: customer.id } : {}),
      });
      setNewKey({ id: data.id, name: data.name, api_key: data.api_key || "" });
      setShowCreate(false);
      load();
    } catch (e) { toast(apiErrorMessage(e, "Erro ao criar máquina."), "error"); }
    finally { setSaving(false); }
  };

  const handleDelete = async (m: Machine) => {
    if (!confirm(`Excluir a máquina "${m.name}"? Todos os equipamentos e backups dela serão perdidos.`)) return;
    try {
      await deleteMachine(m.id);
      toast("Máquina excluída.", "success");
      load();
    } catch (e) { toast(apiErrorMessage(e, "Erro ao excluir máquina."), "error"); }
  };

  const handleBulk = async (action: "restart" | "backup") => {
    const online = machines.filter(m => m.active && m.is_online).length;
    const texto = action === "restart" ? "Reiniciar o agente" : "Iniciar o backup";
    if (!confirm(`${texto} de ${online} máquina(s) online?\nMáquinas offline serão ignoradas.`)) return;
    setBulkBusy(true);
    try {
      const r = action === "restart" ? await restartAgentAll() : await triggerBackupAll();
      toast(`${action === "restart" ? "Reinício" : "Backup"} solicitado para ${r.queued} máquina(s)` +
        (r.skipped_offline ? ` (${r.skipped_offline} offline ignorada(s)).` : "."), "success");
      load();
    } catch { toast("Erro ao enviar o comando em massa.", "error"); }
    finally { setBulkBusy(false); }
  };

  const copyKey = (key: string) => {
    navigator.clipboard.writeText(key).then(
      () => toast("Copiado!", "success"),
      () => toast("Não foi possível copiar.", "error"),
    );
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Máquinas</h1>
          <p className="page-subtitle">{machines.length} máquina(s) cadastrada(s)</p>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-secondary" onClick={() => handleBulk("restart")} disabled={bulkBusy}
            title="Reinicia o agente de todas as máquinas online">
            <RotateCcw size={15} /> Reiniciar todas
          </button>
          <button className="btn btn-secondary" onClick={() => handleBulk("backup")} disabled={bulkBusy}
            title="Dispara o backup em todas as máquinas online">
            <Play size={15} /> Backup de todas
          </button>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <Plus size={15} /> Nova Máquina
          </button>
        </div>
      </div>

      <div className="filters-bar">
        <select className="form-input" value={customerFilter} onChange={e => setCustomerFilter(e.target.value)}
          title="Filtrar por cliente">
          <option value="">Cliente: Todos</option>
          <option value={NO_CUSTOMER}>Sem cliente</option>
          {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      {loading ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : loadFailed && machines.length === 0 ? (
        <div className="empty-state">
          <div>Não foi possível carregar as máquinas.</div>
          <button className="btn btn-secondary mt-2" onClick={() => { setLoading(true); load(); }}>Tentar novamente</button>
        </div>
      ) : machines.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🖥️</div>
          <div>Nenhuma máquina cadastrada ainda.</div>
          <button className="btn btn-primary mt-2" onClick={() => setShowCreate(true)}>Cadastrar agora</button>
        </div>
      ) : visible.length === 0 ? (
        <div className="empty-state">Nenhuma máquina para este filtro.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Máquina</th>
                <th>Cliente</th>
                <th>Status</th>
                <th>Equipamentos</th>
                <th>Horário</th>
                <th>Último backup</th>
                <th>API Key</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((m) => (
                <tr key={m.id}>
                  <td>
                    <Link to={`/maquinas/${m.id}`} style={{ fontWeight: 600, color: "var(--text-primary)" }}>{m.name}</Link>
                    <div className="text-xs text-muted font-mono" style={{ marginTop: 2 }}>{m.id.slice(0, 8)}...</div>
                  </td>
                  <td>
                    {m.customer_id
                      ? <Link to={`/clientes/${m.customer_id}`}>{m.customer_name || "Cliente"}</Link>
                      : <span className="text-muted">—</span>}
                  </td>
                  <td>
                    <StatusBadge status={!m.active ? "DESATIVADO" : m.is_online ? "ONLINE" : "OFFLINE"} />
                  </td>
                  <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{m.nvr_count}</td>
                  <td className="text-secondary" title={m.schedule_from_customer ? "Definido pelo cliente" : "Horário próprio"}>
                    {fmtSchedule(m.backup_hour, m.backup_minute)}
                  </td>
                  <td className="text-secondary text-sm">{fmtDate(m.last_backup_at)}</td>
                  <td><span className="font-mono text-xs text-muted">{m.api_key_prefix}…</span></td>
                  <td>
                    <div className="flex gap-2">
                      <button className="btn-icon" title="Abrir máquina" onClick={() => navigate(`/maquinas/${m.id}`)}>
                        <Eye size={14} />
                      </button>
                      <button className="btn-icon" title="Excluir máquina" style={{ color: "var(--err)" }}
                        onClick={() => handleDelete(m)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <NewMachineModal
          customers={customers}
          initialCustomerId={customerFilter && customerFilter !== NO_CUSTOMER ? customerFilter : undefined}
          saving={saving}
          onSave={handleCreate}
          onClose={() => setShowCreate(false)}
        />
      )}

      {newKey && (
        <NewMachineKeyModal
          machine={newKey}
          onCopy={copyKey}
          onOpen={() => { setNewKey(null); navigate(`/maquinas/${newKey.id}`); }}
          onClose={() => setNewKey(null)}
        />
      )}
    </>
  );
}
