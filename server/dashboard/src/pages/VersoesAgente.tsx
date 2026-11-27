import { useEffect, useMemo, useState } from "react";
import { fetchAgentVersions, createAgentVersion, toggleAgentVersion, deleteAgentVersion, editAgentVersion } from "../api/client";
import { useToast } from "../components/Toast";
import { useConfirm } from "../components/ConfirmDialog";
import MenuAcoes from "../components/MenuAcoes";
import { AgentVersion } from "../api/types";
import { apiErrorMessage } from "../utils/errors";
import { Edit2, Power, PowerOff, Trash2, UploadCloud } from "lucide-react";

// Versões do agente (OTA). Saiu de Configurações em 26/11/2026: com ~50 versões a página tinha 6.000 px.
// Mostra a versão que os agentes recebem e as últimas; o resto fica em "Mostrar todas".
const QTD_RECENTES = 5;

const formVazio = { version: "", url_service: "", sha256_service: "", url_tray: "", sha256_tray: "" };

function parse(v: string): number[] {
  return v.split(".").map(x => parseInt(x, 10) || 0);
}

function compararVersao(a: string, b: string): number {
  const pa = parse(a), pb = parse(b);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}

function encurtar(hash?: string | null): string {
  return hash ? `${hash.slice(0, 12)}…` : "—";
}

export default function VersoesAgente() {
  const [versions, setVersions] = useState<AgentVersion[] | null>(null);
  const [todas, setTodas] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState(formVazio);
  const [createForm, setCreateForm] = useState(formVazio);
  const { toast } = useToast();
  const confirmar = useConfirm();

  const carregar = () =>
    fetchAgentVersions()
      .then((v: AgentVersion[]) => setVersions(v))
      .catch(() => { setVersions([]); toast("Erro ao carregar as versões do agente.", "error"); });

  useEffect(() => { carregar(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Os agentes recebem a MAIOR versão ativa (routers/agent_update.py), não a última cadastrada
  const ordenadas = useMemo(
    () => [...(versions ?? [])].sort((a, b) => compararVersao(b.version, a.version)),
    [versions],
  );
  const emUso = ordenadas.find(v => v.active) ?? null;
  const emUsoLinux = ordenadas.find(v => v.active && v.url_linux && v.sha256_linux) ?? null;
  const exibidas = todas ? ordenadas : ordenadas.slice(0, QTD_RECENTES);

  const handleDelete = async (v: AgentVersion) => {
    if (!(await confirmar({
      title: "Apagar versão do agente",
      message: `Apagar a versão ${v.version} para sempre? Esta ação não pode ser desfeita.`,
      confirmLabel: "Apagar versão",
      variant: "danger",
    }))) return;
    try {
      await deleteAgentVersion(v.id);
      toast("Versão apagada!", "success");
      carregar();
    } catch { toast("Erro ao apagar.", "error"); }
  };

  const handleToggle = async (v: AgentVersion) => {
    if (!v.active || v.id !== emUso?.id || (await confirmar({
      title: "Pausar a versão em uso",
      message: `Pausar a ${v.version}? Os agentes passam a receber a maior versão ativa abaixo dela (quem já atualizou continua na ${v.version}).`,
      confirmLabel: "Pausar",
      variant: "warning",
    }))) {
      try {
        await toggleAgentVersion(v.id);
        carregar();
      } catch { toast("Erro ao alterar.", "error"); }
    }
  };

  const startEdit = (v: AgentVersion) => {
    setEditingId(v.id);
    setEditForm({ version: v.version, url_service: v.url_service, sha256_service: v.sha256_service, url_tray: v.url_tray || "", sha256_tray: v.sha256_tray || "" });
  };

  const handleEditSave = async (id: string) => {
    try {
      await editAgentVersion(id, editForm);
      toast("Versão atualizada!", "success");
      setEditingId(null);
      carregar();
    } catch (e) { toast(apiErrorMessage(e, "Erro ao editar."), "error"); }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createAgentVersion(createForm);
      toast("Nova versão registrada!", "success");
      setCreateForm(formVazio);
      carregar();
    } catch (err) { toast(apiErrorMessage(err, "Erro ao criar versão."), "error"); }
  };

  const campo = (id: string, rotulo: string, valor: string, mudar: (v: string) => void, extra: Partial<React.InputHTMLAttributes<HTMLInputElement>> = {}) => (
    <div className="form-group" style={{ flex: "1 1 220px", marginBottom: 0 }}>
      <label className="form-label" htmlFor={id}>{rotulo}</label>
      <input id={id} className="form-input" value={valor} onChange={e => mudar(e.target.value)} {...extra} />
    </div>
  );

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Versões do agente</h1>
          <p className="page-subtitle">Atualização automática dos agentes (os agentes conferem a cada hora)</p>
        </div>
      </div>

      {versions === null ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : (
        <div style={{ display: "grid", gap: 20, maxWidth: 1100 }}>
          {/* Resumo: o que os agentes recebem hoje */}
          <div className="stats-grid" style={{ marginBottom: 0 }}>
            <div className="stat-card purple">
              <div className="stat-label">Versão oferecida (Windows)</div>
              <div className="stat-value purple">{emUso ? emUso.version : "—"}</div>
            </div>
            <div className="stat-card cyan">
              <div className="stat-label">Versão oferecida (Mikrotik)</div>
              <div className="stat-value cyan">{emUsoLinux ? emUsoLinux.version : "—"}</div>
            </div>
            <div className="stat-card green">
              <div className="stat-label">Versões cadastradas</div>
              <div className="stat-value green">{ordenadas.length}</div>
            </div>
          </div>

          <div className="card">
            <div className="section-title"><UploadCloud size={15} /> {todas ? "Todas as versões" : `Últimas ${Math.min(QTD_RECENTES, ordenadas.length)} versões`}</div>
            {ordenadas.length === 0 ? (
              <p className="text-sm text-muted">Nenhuma versão cadastrada.</p>
            ) : (
              <div className="table-wrap">
                <table className="tabela-cartoes">
                  <thead>
                    <tr>
                      <th>Versão</th>
                      <th>Situação</th>
                      <th>Arquivos</th>
                      <th>Conferência (SHA-256)</th>
                      <th>Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {exibidas.map(v => editingId === v.id ? (
                      <tr key={v.id}>
                        <td colSpan={5} data-label="">
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
                            {campo(`ed-versao-${v.id}`, "Versão", editForm.version, x => setEditForm({ ...editForm, version: x }))}
                            {campo(`ed-url-s-${v.id}`, "Link do Service", editForm.url_service, x => setEditForm({ ...editForm, url_service: x }))}
                            {campo(`ed-sha-s-${v.id}`, "SHA-256 do Service", editForm.sha256_service, x => setEditForm({ ...editForm, sha256_service: x }))}
                            {campo(`ed-url-t-${v.id}`, "Link do Tray", editForm.url_tray, x => setEditForm({ ...editForm, url_tray: x }))}
                            {campo(`ed-sha-t-${v.id}`, "SHA-256 do Tray", editForm.sha256_tray, x => setEditForm({ ...editForm, sha256_tray: x }))}
                            <div className="flex gap-2">
                              <button onClick={() => handleEditSave(v.id)} className="btn btn-primary">Salvar</button>
                              <button onClick={() => setEditingId(null)} className="btn btn-secondary">Cancelar</button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      <tr key={v.id}>
                        <td data-label=""><strong>{v.version}</strong></td>
                        <td data-label="Situação">
                          {v.id === emUso?.id
                            ? <span className="badge ok"><span className="dot ok" /> Em uso</span>
                            : v.active
                              ? <span className="badge muted">Ativa</span>
                              : <span className="badge warn">Pausada</span>}
                        </td>
                        <td data-label="Arquivos">
                          <span style={{ display: "inline-flex", gap: 10, flexWrap: "wrap" }}>
                            <a href={v.url_service} target="_blank" rel="noreferrer">Service</a>
                            {v.url_tray && <a href={v.url_tray} target="_blank" rel="noreferrer">Tray</a>}
                            {v.url_linux && <a href={v.url_linux} target="_blank" rel="noreferrer">Mikrotik</a>}
                          </span>
                        </td>
                        <td data-label="SHA-256" className="font-mono text-xs text-muted"
                          title={[`Service: ${v.sha256_service}`, v.sha256_tray && `Tray: ${v.sha256_tray}`, v.sha256_linux && `Mikrotik: ${v.sha256_linux}`].filter(Boolean).join("\n")}>
                          S {encurtar(v.sha256_service)}
                          {v.sha256_tray && <><br />T {encurtar(v.sha256_tray)}</>}
                          {v.sha256_linux && <><br />L {encurtar(v.sha256_linux)}</>}
                        </td>
                        <td data-label="">
                          <MenuAcoes compacto rotulo={`Ações da versão ${v.version}`} acoes={[
                            { rotulo: "Editar", icone: <Edit2 size={14} />, onClick: () => startEdit(v) },
                            {
                              rotulo: v.active ? "Pausar" : "Ativar",
                              icone: v.active ? <PowerOff size={14} /> : <Power size={14} />,
                              onClick: () => handleToggle(v),
                            },
                            { rotulo: "Apagar versão", icone: <Trash2 size={14} />, onClick: () => handleDelete(v), perigo: true },
                          ]} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {ordenadas.length > QTD_RECENTES && (
              <button className="btn btn-secondary mt-3" onClick={() => setTodas(t => !t)}>
                {todas ? `Mostrar só as últimas ${QTD_RECENTES}` : `Mostrar todas (${ordenadas.length})`}
              </button>
            )}
          </div>

          {/* Cadastro manual: o normal é o publish_version.ps1, que calcula os hashes */}
          <details className="card">
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>Cadastrar versão manualmente</summary>
            <p className="text-sm text-muted mt-2">
              O normal é cadastrar pelo script <code>publish_version.ps1</code>, que calcula os SHA-256 dos arquivos.
              O cadastro libera a versão para todos os agentes.
            </p>
            <form onSubmit={handleCreate} className="mt-3" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
              {campo("nv-versao", "Versão", createForm.version, x => setCreateForm({ ...createForm, version: x }), { placeholder: "ex.: 1.1.71", required: true })}
              {campo("nv-url-s", "Link do Service", createForm.url_service, x => setCreateForm({ ...createForm, url_service: x }), { type: "url", required: true, placeholder: "https://…/TrilanAgentService.exe" })}
              {campo("nv-sha-s", "SHA-256 do Service", createForm.sha256_service, x => setCreateForm({ ...createForm, sha256_service: x }), { required: true })}
              {campo("nv-url-t", "Link do Tray (opcional)", createForm.url_tray, x => setCreateForm({ ...createForm, url_tray: x }), { type: "url", placeholder: "https://…/TrilanAgentTray.exe" })}
              {campo("nv-sha-t", "SHA-256 do Tray (opcional)", createForm.sha256_tray, x => setCreateForm({ ...createForm, sha256_tray: x }))}
              <button type="submit" className="btn btn-primary">Cadastrar versão</button>
            </form>
          </details>
        </div>
      )}
    </>
  );
}
