import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchSettings, updateSettings } from "../api/client";
import { useToast } from "../components/Toast";
import { apiErrorMessage } from "../utils/errors";
import { Save, Mail, Lock, Database, UploadCloud } from "lucide-react";

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
    } catch (err) {
      // Mostra o motivo (ex.: "A senha deve ter pelo menos 10 caracteres."), não só a falha genérica
      toast(apiErrorMessage(err, "Erro ao salvar."), "error");
    }
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

        {/* As versões do agente têm página própria desde 26/11/2026 */}
        <div className="card">
          <div className="section-title"><UploadCloud size={15} />Versões do agente</div>
          <p className="text-sm text-muted">
            A atualização automática dos agentes fica em <Link to="/versoes-agente">Versões do agente</Link>.
          </p>
        </div>
      </div>
    </>
  );
}
