import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchCustomers, createCustomer, deleteCustomer } from "../../api/client";
import { Customer } from "../../api/types";
import { useToast } from "../../components/Toast";
import { fmtDate, fmtSchedule } from "../../utils/date";
import { apiErrorMessage } from "../../utils/errors";
import { Plus, Trash2, Eye } from "lucide-react";
import HealthBadge, { QueueBadge } from "./components/HealthBadge";
import CustomerFormModal, { CustomerForm, emptyCustomerForm, parseEmailList } from "./components/CustomerFormModal";

// Lista plana de Clientes: um clique abre o detalhe (/clientes/:id)
export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  const load = useCallback(() =>
    fetchCustomers()
      .then((c) => { setCustomers(c); setLoadFailed(false); })
      .catch(() => { setLoadFailed(true); toast("Erro ao carregar clientes.", "error"); })
      .finally(() => setLoading(false)),
  [toast]);

  useEffect(() => {
    load();
    // Polling silencioso para refletir status da fila e das máquinas
    const interval = setInterval(() => {
      fetchCustomers().then(setCustomers).catch(() => { /* tenta de novo no próximo ciclo */ });
    }, 10000);
    return () => clearInterval(interval);
  }, [load]);

  const handleCreate = async (form: CustomerForm) => {
    if (!form.name.trim()) { toast("Nome obrigatório.", "error"); return; }
    setSaving(true);
    try {
      const c = await createCustomer({
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        backup_hour: form.backup_hour,
        backup_minute: form.backup_minute,
        email_to: parseEmailList(form.email_to),
        active: true,
        zip_password: form.password_mode === "custom" && form.zip_password?.trim() ? form.zip_password.trim() : undefined,
      });
      toast("Cliente criado!", "success");
      setShowCreate(false);
      navigate(`/clientes/${c.id}`);
    } catch (e) { toast(apiErrorMessage(e, "Erro ao criar cliente."), "error"); }
    finally { setSaving(false); }
  };

  const handleDelete = async (c: Customer) => {
    const msg = c.machines_total > 0
      ? `Excluir o cliente "${c.name}"?\nAs ${c.machines_total} máquina(s) dele continuam cadastradas, mas ficarão sem cliente.`
      : `Excluir o cliente "${c.name}"?`;
    if (!confirm(msg)) return;
    try {
      await deleteCustomer(c.id);
      toast("Cliente excluído.", "success");
      load();
    } catch (e) { toast(apiErrorMessage(e, "Erro ao excluir cliente."), "error"); }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Clientes</h1>
          <p className="page-subtitle">{customers.length} cliente(s) cadastrado(s)</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <Plus size={15} /> Novo Cliente
        </button>
      </div>

      {loading ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : loadFailed && customers.length === 0 ? (
        <div className="empty-state">
          <div>Não foi possível carregar os clientes.</div>
          <button className="btn btn-secondary mt-2" onClick={() => { setLoading(true); load(); }}>Tentar novamente</button>
        </div>
      ) : customers.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🏢</div>
          <div>Nenhum cliente cadastrado.</div>
          <button className="btn btn-primary mt-2" onClick={() => setShowCreate(true)}>Cadastrar agora</button>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Saúde</th>
                <th>Máquinas online</th>
                <th>Horário diário</th>
                <th>Último backup</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {customers.map(c => (
                <tr key={c.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/clientes/${c.id}`)}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{c.name}</span>
                      {c.queue_active && <QueueBadge />}
                    </div>
                    {c.description && <div className="text-xs text-muted" style={{ marginTop: 2 }}>{c.description}</div>}
                  </td>
                  <td><HealthBadge health={c.health} /></td>
                  <td>
                    <span style={{ fontWeight: 600, color: c.machines_total === 0 ? "var(--text-muted)" : c.machines_online > 0 ? "var(--ok)" : "var(--err)" }}>
                      {c.machines_online}/{c.machines_total}
                    </span>
                  </td>
                  <td className="text-secondary">{fmtSchedule(c.backup_hour, c.backup_minute)}</td>
                  <td className="text-secondary text-sm">{fmtDate(c.last_backup_at)}</td>
                  <td onClick={e => e.stopPropagation()}>
                    <div className="flex gap-2">
                      <button className="btn-icon" title="Abrir cliente" onClick={() => navigate(`/clientes/${c.id}`)}>
                        <Eye size={14} />
                      </button>
                      <button className="btn-icon" title="Excluir cliente" style={{ color: "var(--err)" }} onClick={() => handleDelete(c)}>
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
        <CustomerFormModal
          title="Novo Cliente"
          initial={emptyCustomerForm()}
          saving={saving}
          onSave={handleCreate}
          onClose={() => setShowCreate(false)}
        />
      )}
    </>
  );
}
