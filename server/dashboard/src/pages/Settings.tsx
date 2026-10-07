import { useEffect, useState } from "react";
import { fetchSettings, updateSettings, fetchAgentVersions, createAgentVersion, toggleAgentVersion, deleteAgentVersion } from "../api/client";
import { useToast } from "../components/Toast";
import { Save, Mail, Lock, Database, UploadCloud, Trash2, Power, PowerOff } from "lucide-react";

function OtaManager() {
  const [versions, setVersions] = useState<any[]>([]);
  const { toast } = useToast();

  const loadVersions = () => fetchAgentVersions().then(setVersions).catch(() => toast("Erro ao carregar OTA", "error"));

  useEffect(() => { loadVersions(); }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("Deletar esta versão para sempre?")) return;
    try {
      await deleteAgentVersion(id);
      toast("Versão apagada!", "success");
      loadVersions();
    } catch { toast("Erro ao apagar.", "error"); }
  };

  const handleToggle = async (id: string) => {
    try {
      await toggleAgentVersion(id);
      loadVersions();
    } catch { toast("Erro ao alterar.", "error"); }
  };

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ version: "", url_service: "", sha256_service: "", url_tray: "", sha256_tray: "" });
  const [createForm, setCreateForm] = useState({ version: "", url_service: "", sha256_service: "", url_tray: "", sha256_tray: "" });

  const startEdit = (v: any) => {
    setEditingId(v.id);
    setEditForm({ version: v.version, url_service: v.url_service, sha256_service: v.sha256_service, url_tray: v.url_tray || "", sha256_tray: v.sha256_tray || "" });
  };

  const handleEditSave = async (id: string) => {
    try {
      // Aqui usamos a rota/função correspondente, garantindo envio dos novos campos
      await fetch(`/api/v1/admin/agent-versions/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + localStorage.getItem("trilan_token") },
        body: JSON.stringify(editForm)
      });
      toast("Versão atualizada!", "success");
      setEditingId(null);
      loadVersions();
    } catch { toast("Erro ao editar.", "error"); }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createAgentVersion(createForm);
      toast("Nova versão registrada com sucesso!", "success");
      setCreateForm({ version: "", url_service: "", sha256_service: "", url_tray: "", sha256_tray: "" });
      loadVersions();
    } catch { toast("Erro ao criar versão.", "error"); }
  };

  return (
    <div className="card mt-4" style={{ overflowX: 'auto' }}>
      <div className="section-title"><UploadCloud size={15} />Gerenciador de Versões OTA (Agent)</div>
      
      {/* Formulário de Criação */}
      <form onSubmit={handleCreate} className="mt-2 mb-4" style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
        <div className="flex gap-3">
          <div className="form-group" style={{ flex: 1 }}>
            <label className="form-label">Versão</label>
            <input className="form-input" placeholder="ex: 1.0.4" required value={createForm.version} onChange={e => setCreateForm({...createForm, version: e.target.value})} />
          </div>
          <div className="form-group" style={{ flex: 2 }}>
            <label className="form-label">Service SHA256 (Service)</label>
            <input className="form-input" placeholder="Hash do TrilanAgentService.exe" required value={createForm.sha256_service} onChange={e => setCreateForm({...createForm, sha256_service: e.target.value})} />
          </div>
          <div className="form-group" style={{ flex: 2 }}>
            <label className="form-label">URL (Service)</label>
            <input className="form-input" placeholder="https://...TrilanAgentService.exe" type="url" required value={createForm.url_service} onChange={e => setCreateForm({...createForm, url_service: e.target.value})} />
          </div>
        </div>
        
        <div className="flex gap-3 align-items-end">
          <div className="form-group" style={{ flex: 2 }}>
            <label className="form-label">Tray SHA256 (Opcional)</label>
            <input className="form-input" placeholder="Hash do TrilanAgentTray.exe" value={createForm.sha256_tray} onChange={e => setCreateForm({...createForm, sha256_tray: e.target.value})} />
          </div>
          <div className="form-group" style={{ flex: 2, marginBottom: 0 }}>
            <label className="form-label">URL (Tray) (Opcional)</label>
            <input className="form-input" placeholder="https://...TrilanAgentTray.exe" type="url" value={createForm.url_tray} onChange={e => setCreateForm({...createForm, url_tray: e.target.value})} />
          </div>
          <button type="submit" className="btn btn-primary" style={{ height: '38px', padding: '0 20px', flexShrink: 0 }}>
            Registrar Nova Versão
          </button>
        </div>
      </form>

      {versions.length === 0 ? (
        <p className="text-sm text-muted">Nenhuma versão publicada no banco de dados.</p>
      ) : (
        <table className="table" style={{ marginTop: 10, minWidth: 900 }}>
          <thead>
            <tr>
              <th>Versão</th>
              <th>SHA256 (Service / Tray)</th>
              <th>URL do Executável</th>
              <th>Status</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {versions.map(v => (
              <tr key={v.id}>
                {editingId === v.id ? (
                  <>
                    <td><input className="input" value={editForm.version} onChange={e => setEditForm({...editForm, version: e.target.value})} /></td>
                    <td>
                      <input className="input" style={{marginBottom: 4}} placeholder="Hash Service" value={editForm.sha256_service} onChange={e => setEditForm({...editForm, sha256_service: e.target.value})} />
                      <input className="input" placeholder="Hash Tray" value={editForm.sha256_tray} onChange={e => setEditForm({...editForm, sha256_tray: e.target.value})} />
                    </td>
                    <td>
                      <input className="input" style={{marginBottom: 4}} placeholder="URL Service" value={editForm.url_service} onChange={e => setEditForm({...editForm, url_service: e.target.value})} />
                      <input className="input" placeholder="URL Tray" value={editForm.url_tray} onChange={e => setEditForm({...editForm, url_tray: e.target.value})} />
                    </td>
                    <td>—</td>
                    <td>
                      <div className="flex gap-2">
                        <button onClick={() => handleEditSave(v.id)} className="btn btn-sm btn-primary">Salvar</button>
                        <button onClick={() => setEditingId(null)} className="btn btn-sm btn-secondary">Cancelar</button>
                      </div>
                    </td>
                  </>
                ) : (
                  <>
                    <td><strong>{v.version}</strong></td>
                    <td style={{ fontSize: 11, fontFamily: "monospace", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis" }}>
                      S: {v.sha256_service}<br/>
                      {v.sha256_tray && <span>T: {v.sha256_tray}</span>}
                    </td>
                    <td style={{ fontSize: 11, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      <a href={v.url_service} target="_blank" rel="noreferrer" title={v.url_service}>⬇ Service</a>
                      {v.url_tray && <><br/><a href={v.url_tray} target="_blank" rel="noreferrer" title={v.url_tray}>⬇ Tray</a></>}
                    </td>
                    <td>
                      <span className={`badge ${v.active ? 'badge-success' : 'badge-danger'}`}>
                        {v.active ? "Ativa" : "Pausada"}
                      </span>
                    </td>
                    <td>
                      <div className="flex gap-2">
                        <button onClick={() => startEdit(v)} className="btn btn-sm btn-primary" title="Editar">
                          Editar
                        </button>
                        <button onClick={() => handleToggle(v.id)} className="btn btn-sm btn-secondary" title="Pausar/Ativar">
                          {v.active ? <PowerOff size={14} /> : <Power size={14} />}
                        </button>
                        <button onClick={() => handleDelete(v.id)} className="btn btn-sm btn-danger" title="Apagar">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-sm text-muted mt-3">
        Nota: A criação de novas versões continua sendo feita pelo script `publish_version.ps1` no terminal, pois ele precisa calcular o SHA256 do arquivo localmente antes de enviar para cá.
      </p>
    </div>
  );
}

export default function Settings() {
  const [form, setForm] = useState({
    smtp_server: "", smtp_port: "587", smtp_email: "", smtp_password: "",
    retention_days: "30", admin_password_hash: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    fetchSettings().then(data => {
      setForm(f => ({ ...f, ...Object.fromEntries(Object.entries(data).filter(([,v]) => v !== null)) }));
      setLoading(false);
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload: Record<string, string> = {};
      for (const [k, v] of Object.entries(form)) {
        if (v) payload[k] = v;
      }
      await updateSettings(payload);
      toast("Configurações salvas!", "success");
    } catch { toast("Erro ao salvar.", "error"); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="loading-state"><div className="spinner" /></div>;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Configurações</h1>
          <p className="page-subtitle">Configurações globais do sistema</p>
        </div>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? <span className="spinner spinner-sm" /> : <><Save size={15} /> Salvar</>}
        </button>
      </div>

      <div style={{ display: "grid", gap: 20, maxWidth: 680 }}>
        {/* SMTP */}
        <div className="card">
          <div className="section-title"><Mail size={15} />Configurações de E-mail (SMTP)</div>
          <div className="flex gap-3">
            <div className="form-group" style={{ flex: 2 }}>
              <label className="form-label">Servidor SMTP</label>
              <input className="form-input" placeholder="smtp.gmail.com"
                value={form.smtp_server} onChange={e => setForm({ ...form, smtp_server: e.target.value })} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Porta</label>
              <input className="form-input" placeholder="587"
                value={form.smtp_port} onChange={e => setForm({ ...form, smtp_port: e.target.value })} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">E-mail remetente</label>
            <input className="form-input" type="email" placeholder="noreply@empresa.com"
              value={form.smtp_email} onChange={e => setForm({ ...form, smtp_email: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">Senha / App Password</label>
            <input className="form-input" type="password" placeholder="••••••••••••"
              value={form.smtp_password} onChange={e => setForm({ ...form, smtp_password: e.target.value })} />
          </div>
        </div>

        {/* Retention */}
        <div className="card">
          <div className="section-title"><Database size={15} />Retenção de Backups</div>
          <div className="form-group">
            <label className="form-label">Manter backups por (dias)</label>
            <input className="form-input" type="number" min={1} max={365}
              value={form.retention_days} onChange={e => setForm({ ...form, retention_days: e.target.value })}
              style={{ maxWidth: 120 }} />
          </div>
          <p className="text-sm text-muted">
            Backups mais antigos que o limite serão removidos automaticamente do disco do servidor.
          </p>
        </div>

        {/* Admin password */}
        <div className="card">
          <div className="section-title"><Lock size={15} />Segurança</div>
          <div className="form-group">
            <label className="form-label">Nova senha de administrador</label>
            <input className="form-input" type="password" placeholder="Nova senha (vazio = manter atual)"
              value={form.admin_password_hash}
              onChange={e => setForm({ ...form, admin_password_hash: e.target.value })} />
          </div>
          <p className="text-sm text-muted">
            Deixe em branco para não alterar a senha atual.
          </p>
        </div>

        <OtaManager />
      </div>
    </>
  );
}
