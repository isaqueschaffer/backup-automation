import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchSettings, updateSettings } from "../api/client";
import { useToast } from "../components/Toast";
import { apiErrorMessage } from "../utils/errors";
import { Save, Mail, Lock, Database, UploadCloud } from "lucide-react";

// Configurações da plataforma (só administrador da plataforma). Desde 26/11/2026 só o que é configuração:
// e-mail de envio, retenção e senha. As versões do agente têm página própria (/versoes-agente).
type Form = {
  smtp_server: string;
  smtp_port: string;
  smtp_email: string;
  smtp_password: string;
  retention_days: string;
  admin_password_hash: string; // nome do campo no contrato da API: recebe a NOVA senha em texto (vira hash lá)
};

const VAZIO: Form = {
  smtp_server: "", smtp_port: "587", smtp_email: "", smtp_password: "",
  retention_days: "30", admin_password_hash: "",
};

export default function Settings() {
  const [form, setForm] = useState<Form>(VAZIO);
  const [salvo, setSalvo] = useState<Form>(VAZIO);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  const carregar = () => {
    setLoading(true);
    setLoadFailed(false);
    fetchSettings()
      .then((data: Record<string, string | null>) => {
        const lido = { ...VAZIO, ...Object.fromEntries(Object.entries(data).filter(([, v]) => v !== null)) } as Form;
        setForm(lido);
        setSalvo(lido);
      })
      .catch(() => setLoadFailed(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => { carregar(); }, []);

  const alterado = useMemo(
    () => (Object.keys(form) as (keyof Form)[]).some(k => form[k] !== salvo[k]),
    [form, salvo],
  );

  const mudar = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }));

  const handleSave = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setSaving(true);
    try {
      // Só o que mudou; senhas em branco = manter as atuais
      const payload: Record<string, string> = {};
      for (const k of Object.keys(form) as (keyof Form)[]) {
        if (form[k] && form[k] !== salvo[k]) payload[k] = form[k];
      }
      await updateSettings(payload);
      const limpo = { ...form, smtp_password: "", admin_password_hash: "" };
      setForm(limpo);
      setSalvo(limpo);
      toast("Configurações salvas!", "success");
    } catch (err) {
      // Mostra o motivo (ex.: "A senha deve ter pelo menos 10 caracteres."), não só a falha genérica
      toast(apiErrorMessage(err, "Erro ao salvar."), "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="loading-state"><div className="spinner" /></div>;
  if (loadFailed) {
    return (
      <div className="empty-state">
        <div>Não foi possível carregar as configurações.</div>
        <button className="btn btn-secondary mt-2" onClick={carregar}>Tentar novamente</button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSave}>
      <div className="page-header">
        <div>
          <h1 className="page-title">Configurações</h1>
          <p className="page-subtitle">E-mail de envio dos relatórios, tempo de guarda dos backups e senha da plataforma</p>
        </div>
        <div className="flex gap-2" style={{ alignItems: "center" }}>
          {alterado && <span className="text-sm text-muted">Alterações não salvas</span>}
          <button type="submit" className="btn btn-primary" disabled={saving || !alterado}>
            {saving ? <span className="spinner spinner-sm" /> : <><Save size={15} /> Salvar</>}
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gap: 20, maxWidth: 680 }}>
        <section className="card" aria-labelledby="cfg-email">
          <div className="section-title" id="cfg-email"><Mail size={15} />E-mail de envio dos relatórios</div>
          <p className="text-sm text-muted" style={{ marginTop: -4, marginBottom: 14 }}>
            Conta usada para mandar os relatórios de backup e os alertas aos clientes.
          </p>
          <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
            <div className="form-group" style={{ flex: "2 1 220px" }}>
              <label className="form-label" htmlFor="cfg-smtp-servidor">Servidor de envio (SMTP)</label>
              <input id="cfg-smtp-servidor" className="form-input" placeholder="smtp.gmail.com" autoComplete="off"
                value={form.smtp_server} onChange={mudar("smtp_server")} />
            </div>
            <div className="form-group" style={{ flex: "1 1 100px" }}>
              <label className="form-label" htmlFor="cfg-smtp-porta">Porta</label>
              <input id="cfg-smtp-porta" className="form-input" placeholder="587" inputMode="numeric"
                value={form.smtp_port} onChange={mudar("smtp_port")} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="cfg-smtp-email">E-mail remetente</label>
            <input id="cfg-smtp-email" className="form-input" type="email" placeholder="noreply@empresa.com" autoComplete="off"
              value={form.smtp_email} onChange={mudar("smtp_email")} />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" htmlFor="cfg-smtp-senha">Senha do e-mail (no Gmail, a senha de app)</label>
            <input id="cfg-smtp-senha" className="form-input" type="password" autoComplete="new-password"
              placeholder="Em branco = manter a senha atual"
              value={form.smtp_password} onChange={mudar("smtp_password")} />
          </div>
        </section>

        <section className="card" aria-labelledby="cfg-retencao">
          <div className="section-title" id="cfg-retencao"><Database size={15} />Tempo de guarda dos backups</div>
          <div className="form-group">
            <label className="form-label" htmlFor="cfg-dias">Manter os backups por (dias)</label>
            <input id="cfg-dias" className="form-input" type="number" min={1} max={365}
              value={form.retention_days} onChange={mudar("retention_days")} style={{ maxWidth: 120 }} />
          </div>
          <p className="text-sm text-muted">
            Backups mais antigos que isso são apagados sozinhos do disco do servidor.
          </p>
        </section>

        <section className="card" aria-labelledby="cfg-seguranca">
          <div className="section-title" id="cfg-seguranca"><Lock size={15} />Senha do administrador da plataforma</div>
          <div className="form-group">
            <label className="form-label" htmlFor="cfg-senha-admin">Nova senha</label>
            <input id="cfg-senha-admin" className="form-input" type="password" autoComplete="new-password"
              placeholder="Em branco = manter a senha atual"
              value={form.admin_password_hash} onChange={mudar("admin_password_hash")} />
          </div>
          <p className="text-sm text-muted">Use pelo menos 10 caracteres, misturando letras, números e símbolos.</p>
        </section>

        <section className="card" aria-labelledby="cfg-versoes">
          <div className="section-title" id="cfg-versoes"><UploadCloud size={15} />Versões do agente</div>
          <p className="text-sm text-muted">
            A atualização automática dos agentes fica na página <Link to="/versoes-agente">Versões do agente</Link>.
          </p>
        </section>
      </div>
    </form>
  );
}
