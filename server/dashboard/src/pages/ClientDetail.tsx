import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  fetchEquipamentos, createEquipamento, deleteEquipamento, updateClient,
  rotateKey, fetchBackups, restartAgent
} from "../api/client";
import { Client, NVR, Backup, TipoEquipamento } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import Modal from "../components/Modal";
import { useToast } from "../components/Toast";
import {
  ArrowLeft, Plus, Trash2, RefreshCw, Copy, Edit2, Server,
  Archive, RotateCcw, Clock, Mail, CalendarCheck, KeyRound,
  Wifi, WifiOff, Video, FolderOpen, ChevronRight, Phone
} from "lucide-react";

function fmtDate(s: string | null) {
  if (!s) return "—";
  return new Date(s).toLocaleString("pt-BR");
}

function MiniCalendar({ mapStr, referenceDate }: { mapStr: string; referenceDate: string | null }) {
  if (!mapStr) return <span>—</span>;
  const refDate = referenceDate ? new Date(referenceDate) : new Date();
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "4px", width: "fit-content" }}>
      {mapStr.split("").map((char, i) => {
        const isOk = char === "█";
        const daysAgo = (mapStr.length - 1) - i;
        const d = new Date(refDate);
        d.setDate(d.getDate() - daysAgo);
        const dateStr = d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
        return (
          <div key={i} title={`${dateStr}: ${isOk ? "Gravou" : "Falhou"}`}
            style={{
              width: 26, height: 18, flexShrink: 0, borderRadius: 2,
              backgroundColor: isOk ? "var(--ok)" : "var(--err)",
              border: "1px solid rgba(255,255,255,0.15)", color: "white",
              display: "flex", cursor: "help", transition: "transform 0.1s",
              alignItems: "center", justifyContent: "center"
            }}
            onMouseEnter={e => e.currentTarget.style.transform = "scale(1.15)"}
            onMouseLeave={e => e.currentTarget.style.transform = "scale(1)"}
          >
            <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "-0.3px" }}>{dateStr}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Info pill component ──────────────────────────────────────────
function InfoPill({ icon, label, value, mono = false, copyValue, onCopy }: {
  icon: React.ReactNode; label: string; value: React.ReactNode;
  mono?: boolean; copyValue?: string; onCopy?: (v: string) => void;
}) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 6,
      background: "var(--surface-2, rgba(255,255,255,0.03))",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-sm)", padding: "14px 16px"
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--text-muted)", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px" }}>
        {icon}{label}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: "var(--text-primary)", fontFamily: mono ? "monospace" : undefined, fontSize: mono ? 12 : 14, fontWeight: 500, wordBreak: "break-all" }}>
          {value}
        </span>
        {copyValue && onCopy && (
          <button className="btn-icon" style={{ flexShrink: 0 }} onClick={() => onCopy(copyValue)}>
            <Copy size={12} />
          </button>
        )}
      </div>
    </div>
  );
}

// ── Equipment card component ─────────────────────────────────────
function EqCard({ eq, onDelete, onViewRecording }: {
  eq: NVR;
  onDelete: () => void;
  onViewRecording: () => void;
}) {
  const TIPO_ICONE: Record<string, React.ReactNode> = {
    NVR: <Video size={18} />, OLT: <Wifi size={18} />, ONU: <WifiOff size={18} />, PABX: <Phone size={18} />
  };
  const TIPO_COLOR: Record<string, string> = {
    NVR: "var(--primary)", OLT: "#10b981", ONU: "#f59e0b", PABX: "#8b5cf6"
  };
  const color = TIPO_COLOR[eq.tipo] || "var(--text-muted)";

  return (
    <div style={{
      background: "var(--surface-2, rgba(255,255,255,0.03))",
      border: "1px solid var(--border)", borderRadius: "var(--radius)",
      padding: "16px 20px", display: "flex", alignItems: "center", gap: 16,
      transition: "border-color 0.15s"
    }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = color)}
      onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--border)")}
    >
      {/* Icon */}
      <div style={{
        width: 42, height: 42, borderRadius: "var(--radius-sm)", flexShrink: 0,
        background: `${color}18`, border: `1px solid ${color}40`,
        display: "flex", alignItems: "center", justifyContent: "center", color
      }}>
        {TIPO_ICONE[eq.tipo] || <Server size={18} />}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: 14 }}>{eq.name}</span>
          <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: `${color}18`, color, border: `1px solid ${color}30` }}>
            {eq.tipo}
          </span>
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 12 }}>
          {eq.tipo === "OLT" ? (
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <FolderOpen size={12} /> {(eq.config_extra as any)?.pasta_origem || "—"}
            </span>
          ) : (
            <>
              <span style={{ fontFamily: "monospace" }}>{eq.ip}</span>
              {eq.username && <span style={{ display: "flex", alignItems: "center", gap: 3 }}>👤 {eq.username}</span>}
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {eq.tipo === "NVR" && (
          <button className="btn btn-secondary btn-sm" onClick={onViewRecording}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Video size={13} /> Gravações
          </button>
        )}
        <button className="btn-icon" style={{ color: "var(--err)" }} onClick={onDelete}>
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────
export default function ClientDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [client, setClient] = useState<Client | null>(null);
  const [equipamentos, setEquipamentos] = useState<NVR[]>([]);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [loading, setLoading] = useState(true);

  const [showEqModal, setShowEqModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showRecordingModal, setShowRecordingModal] = useState<{ show: boolean, nvrName: string, cameras: any[] }>({ show: false, nvrName: "", cameras: [] });
  const [rotatedKey, setRotatedKey] = useState<string | null>(null);
  const [eqForm, setEqForm] = useState({ tipo: "NVR" as TipoEquipamento, name: "", ip: "", username: "", password: "", pasta_origem: "", fabricante_olt: "UNM2000" });
  const [editForm, setEditForm] = useState<Partial<Client> & { zip_password?: string }>({});
  const [saving, setSaving] = useState(false);

  const TIPOS: TipoEquipamento[] = ["NVR", "OLT", "PABX"];
  const TIPO_ICONE_EMOJI: Record<string, string> = { NVR: "📹", OLT: "🔌", PABX: "📞" };

  const load = async () => {
    if (!id) return;
    const [c, eqs, b] = await Promise.all([
      (await import("../api/client")).fetchClient(id),
      fetchEquipamentos(id),
      fetchBackups({ client_id: id, size: 10 }),
    ]);
    setClient(c); setEquipamentos(eqs); setBackups(b.items);
    setLoading(false);
  };
  useEffect(() => { load(); }, [id]);

  const handleAddEquipamento = async () => {
    if (!eqForm.name) { toast("Preencha o nome do equipamento.", "error"); return; }
    if ((eqForm.tipo === "NVR" || eqForm.tipo === "PABX") && (!eqForm.ip || !eqForm.username || !eqForm.password)) {
      toast(`Para ${eqForm.tipo}, preencha IP/Host, usuário e senha.`, "error"); return;
    }
    if (eqForm.tipo === "OLT" && !eqForm.fabricante_olt) {
      toast("Selecione o sistema da OLT.", "error");
      return;
    }

    if (eqForm.tipo === "OLT" && (eqForm.fabricante_olt === "UNM2000" || eqForm.fabricante_olt === "HUAWEI") && !eqForm.pasta_origem) {
      toast(`Para ${eqForm.fabricante_olt}, informe a pasta de origem dos backups.`, "error");
      return;
    }

    if (eqForm.tipo === "OLT" && eqForm.fabricante_olt === "VSOL" && (!eqForm.pasta_origem || !eqForm.username || !eqForm.password)) {
      toast("Para VSOL, preencha IP, usuário e senha.", "error");
      return;
    }

    setSaving(true);
    try {
      await createEquipamento(id!, {
        tipo: eqForm.tipo,
        name: eqForm.name,
        ip: (eqForm.tipo === "NVR" || eqForm.tipo === "PABX") ? eqForm.ip : (
          eqForm.fabricante_olt === "VSOL" ? eqForm.pasta_origem : eqForm.ip
        ),
        username: eqForm.username,
        password: eqForm.password,
        config_extra: eqForm.tipo === "OLT"
          ? {
            ...((eqForm.fabricante_olt === "UNM2000" || eqForm.fabricante_olt === "HUAWEI")
              ? { pasta_origem: eqForm.pasta_origem }
              : {}),
            fabricante_olt: eqForm.fabricante_olt
          }
          : null,
      });

      toast("Equipamento adicionado!", "success");
      setShowEqModal(false);
      setEqForm({ tipo: "NVR", name: "", ip: "", username: "", password: "", pasta_origem: "", fabricante_olt: "UNM2000" });
      load();
    }
    catch { toast("Erro ao adicionar equipamento.", "error"); }
    finally { setSaving(false); }
  };

  const handleDeleteEquipamento = async (eqId: string, name: string) => {
    if (!confirm(`Remover equipamento "${name}"?`)) return;
    await deleteEquipamento(id!, eqId);
    toast("Equipamento removido.", "success");
    load();
  };

  const handleEditSave = async () => {
    setSaving(true);
    try {
      await updateClient(id!, {
        ...editForm,
        email_to: typeof editForm.email_to === "string"
          ? (editForm.email_to as string).split(",").map(e => e.trim())
          : editForm.email_to,
      });
      toast("Cliente atualizado!", "success");
      setShowEditModal(false);
      load();
    } catch { toast("Erro ao salvar.", "error"); }
    finally { setSaving(false); }
  };

  const handleRotateKey = async () => {
    if (!confirm("Gerar nova API Key? A chave atual será invalidada.")) return;
    const data = await rotateKey(id!);
    setRotatedKey(data.api_key);
    load();
  };

  const handleRestartAgent = async () => {
    if (!confirm("Solicitar reinício do agente? Ele será reiniciado no próximo ping (até 5 min).")) return;
    try {
      await restartAgent(id!);
      toast("Reinício agendado! O agente será reiniciado no próximo ping.", "success");
    } catch { toast("Erro ao solicitar reinício.", "error"); }
  };

  const isAgentOnline = client && client.active &&
    (client.last_seen && new Date().getTime() - new Date(client.last_seen).getTime() < 15 * 60 * 1000);

  const copyText = (t: string) => { navigator.clipboard.writeText(t); toast("Copiado!", "success"); };

  if (loading) return <div className="loading-state"><div className="spinner" /></div>;
  if (!client) return <div className="empty-state">Cliente não encontrado.</div>;

  return (
    <>
      {/* ── Header ── */}
      <div className="page-header">
        <div className="flex items-center gap-3">
          <button className="btn-icon" onClick={() => navigate("/clients")} title="Voltar">
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="page-title">{client.name}</h1>
            <p className="page-subtitle flex items-center gap-2">
              <StatusBadge status={client.last_backup_status} />
              {client.last_backup_at && `Último backup: ${fmtDate(client.last_backup_at)}`}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-secondary" onClick={() => {
            setEditForm({ ...client, email_to: (client.email_to || []).join(", ") as unknown as string[] });
            setShowEditModal(true);
          }}>
            <Edit2 size={15} /> Editar
          </button>
          <button className="btn btn-secondary" onClick={handleRotateKey}>
            <RefreshCw size={15} /> Rodar API Key
          </button>
          <button className="btn btn-secondary" onClick={handleRestartAgent}
            title={!isAgentOnline ? "Agente offline — o reinício será executado no próximo ping" : "Reiniciar o agente Windows"}>
            <RotateCcw size={15} /> Reiniciar Agent
          </button>
        </div>
      </div>

      {/* ── Layout de duas colunas ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>

        {/* Coluna 1 — Configuração */}
        <div className="card" style={{ padding: "20px 24px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 16, display: "flex", alignItems: "center", gap: 6 }}>
            <Server size={13} /> Configuração do Cliente
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <InfoPill icon={<KeyRound size={11} />} label="Client ID" value={client.id} mono copyValue={client.id} onCopy={copyText} />
            <InfoPill icon={<KeyRound size={11} />} label="API Key (prefixo)" value={`${client.api_key_prefix}…`} mono />
            <InfoPill icon={<Clock size={11} />} label="Horário do Backup"
              value={`${String(client.backup_hour).padStart(2, "0")}:${String(client.backup_minute).padStart(2, "0")} (diário)`} />
            <InfoPill icon={<Mail size={11} />} label="E-mails de Notificação"
              value={(client.email_to || []).join(", ") || "—"} />
          </div>
        </div>

        {/* Coluna 2 — Status */}
        <div className="card" style={{ padding: "20px 24px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 16, display: "flex", alignItems: "center", gap: 6 }}>
            <Wifi size={13} /> Status do Agente
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <InfoPill icon={<Wifi size={11} />} label="Conexão"
              value={<StatusBadge status={isAgentOnline ? "ONLINE" : (client.active ? "OFFLINE" : "DESATIVADO")} />} />
            <InfoPill icon={<CalendarCheck size={11} />} label="Último contato"
              value={client.last_seen ? fmtDate(client.last_seen) : "Nunca"} />
            <InfoPill icon={<Archive size={11} />} label="Último Backup"
              value={<StatusBadge status={client.last_backup_status} />} />
            <InfoPill icon={<CalendarCheck size={11} />} label="Data do Último Backup"
              value={fmtDate(client.last_backup_at)} />
          </div>
        </div>
      </div>

      {/* ── Equipamentos ── */}
      <div style={{ marginBottom: 24 }}>
        <div className="flex items-center justify-between mb-3">
          <div className="section-title mb-0">
            <Server size={15} /> Equipamentos
            <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
              {equipamentos.length}
            </span>
          </div>
          <button className="btn btn-secondary" onClick={() => setShowEqModal(true)}>
            <Plus size={14} /> Adicionar
          </button>
        </div>

        {equipamentos.length === 0 ? (
          <div className="empty-state" style={{ padding: "32px" }}>
            <div className="empty-icon">🖥️</div>
            <div>Nenhum equipamento cadastrado.</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {equipamentos.map(eq => (
              <EqCard key={eq.id} eq={eq}
                onDelete={() => handleDeleteEquipamento(eq.id, eq.name)}
                onViewRecording={() => setShowRecordingModal({ show: true, nvrName: eq.name, cameras: eq.last_recording_status || [] })}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Histórico de Backups ── */}
      <div>
        <div className="section-title">
          <Archive size={15} /> Histórico de Backups
          <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
            últimos 10
          </span>
        </div>
        {backups.length === 0 ? (
          <div className="empty-state" style={{ padding: "32px" }}>
            <div className="empty-icon">📦</div>
            <div>Nenhum backup realizado ainda.</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {backups.map(b => (
              <div key={b.id} style={{
                display: "grid", gridTemplateColumns: "1fr auto auto auto auto",
                alignItems: "center", gap: 16,
                background: "var(--surface-2, rgba(255,255,255,0.02))",
                border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                padding: "12px 20px"
              }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>
                    {fmtDate(b.started_at)}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    via {b.trigger}
                  </div>
                </div>
                <StatusBadge status={b.status} />
                <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>
                  {b.zip_size ? `${(b.zip_size / 1024 / 1024).toFixed(1)} MB` : "—"}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }} title="E-mail enviado">
                  {b.email_sent ? "✅ E-mail" : "—"}
                </div>
                <ChevronRight size={14} style={{ color: "var(--text-muted)", opacity: 0.4 }} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Modal: Adicionar Equipamento ── */}
      {showEqModal && (
        <Modal title="Adicionar Equipamento" onClose={() => setShowEqModal(false)}>
          <div className="form-group">
            <label className="form-label">Tipo de Equipamento *</label>
            <select className="form-input" value={eqForm.tipo}
              onChange={e => setEqForm({ ...eqForm, tipo: e.target.value as TipoEquipamento, pasta_origem: "", fabricante_olt: "UNM2000" })}>
              {TIPOS.map(t => <option key={t} value={t}>{TIPO_ICONE_EMOJI[t]} {t}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Nome *</label>
            <input className="form-input" type="text"
              placeholder={`${eqForm.tipo}_Cliente1`}
              value={eqForm.name} onChange={e => setEqForm({ ...eqForm, name: e.target.value })} />
          </div>
          {(eqForm.tipo === "NVR" || eqForm.tipo === "PABX") && (
            <>
              <div className="form-group">
                <label className="form-label">Endereço IP ou Host *</label>
                <input className="form-input" type="text" placeholder={eqForm.tipo === "PABX" ? "https://192.168.12.2" : "192.168.1.100"}
                  value={eqForm.ip} onChange={e => setEqForm({ ...eqForm, ip: e.target.value })} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">Usuário *</label>
                  <input className="form-input" type="text"
                    value={eqForm.username} onChange={e => setEqForm({ ...eqForm, username: e.target.value })} />
                </div>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">Senha *</label>
                  <input className="form-input" type="password"
                    value={eqForm.password} onChange={e => setEqForm({ ...eqForm, password: e.target.value })} />
                </div>
              </div>
            </>
          )}
          {eqForm.tipo === "OLT" && (
            <>
              <div className="form-group">
                <label className="form-label">Sistema da OLT *</label>
                <select
                  className="form-input"
                  value={eqForm.fabricante_olt}
                  onChange={e =>
                    setEqForm({
                      ...eqForm,
                      fabricante_olt: e.target.value
                    })
                  }
                >
                  <option value="UNM2000">🔵 UNM2000</option>
                  <option value="HUAWEI">🔴 HUAWEI</option>
                  <option value="VSOL">🟢 VSOL</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">
                  {eqForm.fabricante_olt === "VSOL"
                    ? "Endereço IP da OLT *"
                    : "Pasta de Origem dos Backups *"}
                </label>

                <input
                  className="form-input"
                  type="text"
                  placeholder={
                    eqForm.fabricante_olt === "VSOL"
                      ? "192.168.1.100"
                      : "C:\\Users\\Helena\\Documents"
                  }
                  value={eqForm.pasta_origem}
                  onChange={e =>
                    setEqForm({
                      ...eqForm,
                      pasta_origem: e.target.value
                    })
                  }
                />

                {eqForm.fabricante_olt === "VSOL" && (
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 12,
                      marginTop: 12
                    }}
                  >
                    <div className="form-group" style={{ margin: 0 }}>
                      <label className="form-label">
                        Usuário *
                      </label>

                      <input
                        className="form-input"
                        type="text"
                        value={eqForm.username}
                        onChange={e =>
                          setEqForm({
                            ...eqForm,
                            username: e.target.value
                          })
                        }
                      />
                    </div>

                    <div className="form-group" style={{ margin: 0 }}>
                      <label className="form-label">
                        Senha *
                      </label>

                      <input
                        className="form-input"
                        type="password"
                        value={eqForm.password}
                        onChange={e =>
                          setEqForm({
                            ...eqForm,
                            password: e.target.value
                          })
                        }
                      />
                    </div>
                  </div>
                )}

                <span
                  style={{
                    fontSize: 12,
                    color: "var(--text-muted)",
                    marginTop: 4,
                    display: "block"
                  }}
                >
                  {(eqForm.fabricante_olt === "UNM2000" || eqForm.fabricante_olt === "HUAWEI")
                    ? `Pasta onde o ${eqForm.fabricante_olt} exporta os arquivos de backup.`
                    : "Endereço IP, usuário e senha utilizados para acessar a VSOL."
                  }
                </span>
              </div>
            </>
          )}
          <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
            <button className="btn btn-secondary" onClick={() => setShowEqModal(false)}>Cancelar</button>
            <button className="btn btn-primary" onClick={handleAddEquipamento} disabled={saving}>
              {saving ? <span className="spinner spinner-sm" /> : <><Plus size={15} /> Adicionar</>}
            </button>
          </div>
        </Modal>
      )}

      {/* ── Modal: Editar Cliente ── */}
      {showEditModal && (
        <Modal title="Editar Cliente" onClose={() => setShowEditModal(false)}>
          <div className="form-group">
            <label className="form-label">Nome</label>
            <input className="form-input" value={editForm.name || ""}
              onChange={e => setEditForm({ ...editForm, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">Horário do Backup Automático</label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label className="form-label" style={{ fontSize: 11 }}>Hora (0-23)</label>
                <input className="form-input" type="number" min={0} max={23} value={editForm.backup_hour ?? 2}
                  onChange={e => setEditForm({ ...editForm, backup_hour: +e.target.value })} />
              </div>
              <div>
                <label className="form-label" style={{ fontSize: 11 }}>Minuto (0-59)</label>
                <input className="form-input" type="number" min={0} max={59} value={editForm.backup_minute ?? 0}
                  onChange={e => setEditForm({ ...editForm, backup_minute: +e.target.value })} />
              </div>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">E-mails de Notificação (separados por vírgula)</label>
            <input className="form-input" value={editForm.email_to as unknown as string || ""}
              onChange={e => setEditForm({ ...editForm, email_to: e.target.value as unknown as string[] })} />
          </div>
          <div className="form-group">
            <label className="form-label">Nova senha do ZIP <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(vazio = manter atual)</span></label>
            <input className="form-input" type="password" value={editForm.zip_password || ""}
              onChange={e => setEditForm({ ...editForm, zip_password: e.target.value })} />
          </div>
          <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
            <button className="btn btn-secondary" onClick={() => setShowEditModal(false)}>Cancelar</button>
            <button className="btn btn-primary" onClick={handleEditSave} disabled={saving}>
              {saving ? <span className="spinner spinner-sm" /> : "Salvar"}
            </button>
          </div>
        </Modal>
      )}

      {/* ── Modal: Nova API Key ── */}
      {rotatedKey && (
        <Modal title="Nova API Key gerada" onClose={() => setRotatedKey(null)}>
          <div style={{
            background: "var(--warn-bg)", border: "1px solid rgba(245,158,11,0.3)",
            borderRadius: "var(--radius-sm)", padding: "12px 16px", marginBottom: 20,
            color: "var(--warn)", fontSize: 13
          }}>
            ⚠️ Copie agora. Não será exibida novamente. Atualize o agent.conf no cliente.
          </div>
          <div className="api-key-display" style={{ borderColor: "rgba(245,158,11,0.4)" }}>
            <span className="api-key-value" style={{ color: "var(--warn)" }}>{rotatedKey}</span>
            <button className="btn-icon" onClick={() => copyText(rotatedKey)}><Copy size={14} /></button>
          </div>
          <button className="btn btn-primary mt-4 w-full" style={{ justifyContent: "center" }}
            onClick={() => setRotatedKey(null)}>Entendi</button>
        </Modal>
      )}

      {/* ── Modal: Status de Gravação ── */}
      {showRecordingModal.show && (
        <Modal wide={true} title={`Gravação — ${showRecordingModal.nvrName} (${fmtDate(client.last_backup_at)})`}
          onClose={() => setShowRecordingModal({ show: false, nvrName: "", cameras: [] })}>
          {showRecordingModal.cameras.length === 0 ? (
            <div className="empty-state">Sem dados de gravação disponíveis.</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Câmera</th>
                    <th>Rede</th>
                    <th>Gravação</th>
                    <th>Dias Gravados</th>
                    <th>Mapa (15 dias)</th>
                  </tr>
                </thead>
                <tbody>
                  {showRecordingModal.cameras.map((cam, i) => {
                    let rede = cam.status_comunicacao;
                    if (!rede) rede = cam.online ? "ONLINE" : (cam.online === false ? "OFFLINE" : "DESCONHECIDO");
                    let gravacao = cam.status_gravacao;
                    if (!gravacao) {
                      const gravouHoje = cam.mapa ? cam.mapa.endsWith("█") : cam.total_dias > 0;
                      gravacao = gravouHoje ? "COM_GRAVACAO" : "SEM_GRAVACAO";
                    }
                    return (
                      <tr key={i}>
                        <td>{cam.nome || `Canal ${cam.canal}`}</td>
                        <td><StatusBadge status={rede} /></td>
                        <td><StatusBadge status={gravacao} /></td>
                        <td>{cam.total_dias || 0}/15</td>
                        <td><MiniCalendar mapStr={cam.mapa || ""} referenceDate={client.last_backup_at} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Modal>
      )}
    </>
  );
}
