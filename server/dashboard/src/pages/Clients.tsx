import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchClients, createClient, deleteClient } from "../api/client";
import { Client } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import Modal from "../components/Modal";
import { useToast } from "../components/Toast";
import { Plus, Trash2, Eye, Copy } from "lucide-react";

interface NewClientForm {
  name: string; backup_hour: number; backup_minute: number;
  email_to: string; zip_password: string;
}

export default function Clients() {
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newKey, setNewKey] = useState<{ id: string; name: string; api_key: string } | null>(null);
  const [form, setForm] = useState<NewClientForm>({
    name: "", backup_hour: 2, backup_minute: 0, email_to: "", zip_password: "",
  });
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  const load = () => { fetchClients().then(setClients).finally(() => setLoading(false)); };
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    if (!form.name.trim()) { toast("Nome obrigatório.", "error"); return; }
    setSaving(true);
    try {
      const data = await createClient({
        name: form.name,
        backup_hour: form.backup_hour,
        backup_minute: form.backup_minute,
        email_to: form.email_to ? form.email_to.split(",").map(e => e.trim()) : [],
        zip_password: form.zip_password || undefined,
        active: true,
      });
      setNewKey({ id: data.id, name: data.name, api_key: data.api_key });
      setShowCreate(false);
      load();
    } catch { toast("Erro ao criar cliente.", "error"); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Excluir "${name}"? Todos os dados serão perdidos.`)) return;
    await deleteClient(id);
    toast("Cliente removido.", "success");
    load();
  };

  const copyKey = (key: string) => {
    navigator.clipboard.writeText(key);
    toast("Chave copiada!", "success");
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Clientes</h1>
          <p className="page-subtitle">{clients.length} cliente(s) cadastrado(s)</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <Plus size={15} /> Novo Cliente
        </button>
      </div>

      {loading ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : clients.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🏢</div>
          <div>Nenhum cliente cadastrado ainda.</div>
          <button className="btn btn-primary mt-2" onClick={() => setShowCreate(true)}>Cadastrar agora</button>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Status</th>
                <th>Equipamentos</th>
                <th>Horário Backup</th>
                <th>Último Backup</th>
                <th>API Key</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{c.name}</div>
                    <div className="text-xs text-muted font-mono" style={{ marginTop: 2 }}>
                      {c.id.slice(0, 8)}...
                    </div>
                  </td>
                  <td>
                    <StatusBadge status={
                      !c.active ? "DESATIVADO" : 
                      (c.last_seen && new Date().getTime() - new Date(c.last_seen.endsWith("Z") ? c.last_seen : c.last_seen + "Z").getTime() < 15 * 60 * 1000) 
                        ? "ONLINE" 
                        : "OFFLINE"
                    } />
                  </td>
                  <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{c.nvr_count}</td>
                  <td className="text-secondary">
                    {String(c.backup_hour).padStart(2,"0")}:{String(c.backup_minute).padStart(2,"0")}
                  </td>
                  <td className="text-secondary text-sm">
                    {c.last_backup_at ? new Date(c.last_backup_at.endsWith("Z") ? c.last_backup_at : c.last_backup_at + "Z").toLocaleString("pt-BR") : "—"}
                  </td>
                  <td>
                    <span className="font-mono text-xs text-muted">{c.api_key_prefix}…</span>
                  </td>
                  <td>
                    <div className="flex gap-2">
                      <button className="btn-icon" title="Ver detalhes" onClick={() => navigate(`/clients/${c.id}`)}>
                        <Eye size={14} />
                      </button>
                      <button className="btn-icon" title="Excluir" style={{ color: "var(--err)" }}
                        onClick={() => handleDelete(c.id, c.name)}>
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

      {/* Create modal */}
      {showCreate && (
        <Modal title="Novo Cliente" onClose={() => setShowCreate(false)}>
          <div className="form-group">
            <label className="form-label">Nome do Cliente *</label>
            <input className="form-input" placeholder="Ex: Farmácia Central" value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="flex gap-3">
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Hora do backup</label>
              <input className="form-input" type="number" min={0} max={23} value={form.backup_hour}
                onChange={e => setForm({ ...form, backup_hour: +e.target.value })} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Minuto</label>
              <input className="form-input" type="number" min={0} max={59} value={form.backup_minute}
                onChange={e => setForm({ ...form, backup_minute: +e.target.value })} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Destinatários de e-mail (separados por vírgula)</label>
            <input className="form-input" placeholder="ti@empresa.com, gestor@empresa.com"
              value={form.email_to} onChange={e => setForm({ ...form, email_to: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">Senha do ZIP (opcional — gerada automaticamente se vazio)</label>
            <input className="form-input" type="password" placeholder="SenhaForte123"
              value={form.zip_password} onChange={e => setForm({ ...form, zip_password: e.target.value })} />
          </div>
          <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
            <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancelar</button>
            <button className="btn btn-primary" onClick={handleCreate} disabled={saving}>
              {saving ? <span className="spinner spinner-sm" /> : <><Plus size={15} /> Criar</>}
            </button>
          </div>
        </Modal>
      )}

      {/* New key modal */}
      {newKey && (
        <Modal title="Cliente criado com sucesso!" onClose={() => setNewKey(null)} wide>
          <div style={{ background: "var(--warn-bg)", border: "1px solid rgba(245,158,11,0.3)",
            borderRadius: "var(--radius-sm)", padding: "12px 16px", marginBottom: 20,
            color: "var(--warn)", fontSize: 13 }}>
            ⚠️ Copie a API Key agora. Ela não será exibida novamente.
          </div>
          <div className="form-group">
            <label className="form-label">Client ID</label>
            <div className="api-key-display">
              <span className="api-key-value">{newKey.id}</span>
              <button className="btn-icon" onClick={() => copyKey(newKey.id)}><Copy size={14} /></button>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">API Key (salve agora!)</label>
            <div className="api-key-display" style={{ borderColor: "rgba(245,158,11,0.4)" }}>
              <span className="api-key-value" style={{ color: "var(--warn)" }}>{newKey.api_key}</span>
              <button className="btn-icon" onClick={() => copyKey(newKey.api_key)}><Copy size={14} /></button>
            </div>
          </div>
          <p className="text-sm text-muted mt-2">
            Configure o arquivo <span className="font-mono">agent.conf</span> com esses valores no cliente Windows.
          </p>
          <button className="btn btn-primary mt-4 w-full" style={{ justifyContent: "center" }}
            onClick={() => { setNewKey(null); navigate(`/clients/${newKey.id}`); }}>
            <Eye size={15} /> Ver detalhes do cliente
          </button>
        </Modal>
      )}
    </>
  );
}
