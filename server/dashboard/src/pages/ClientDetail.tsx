import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  fetchEquipamentos, createEquipamento, updateEquipamento, deleteEquipamento, updateClient,
  rotateKey, fetchBackups, restartAgent, triggerBackup
} from "../api/client";
import { Client, NVR, Backup, TipoEquipamento } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import Modal from "../components/Modal";
import { useToast } from "../components/Toast";
import api from "../api/client";
import { useRef } from "react";
import { Video } from "lucide-react";
import {
  ArrowLeft, Plus, Trash2, RefreshCw, Copy, Edit2, Server,
  Archive, RotateCcw, Clock, Mail, CalendarCheck, KeyRound,
  Wifi, WifiOff, Video, FolderOpen, ChevronRight, Phone, Network, CloudLightning
} from "lucide-react";

function fmtDate(s: string | null) {
  if (!s) return "â€”";
  const str = s.endsWith("Z") ? s : s + "Z";
  return new Date(str).toLocaleString("pt-BR");
}

function MiniCalendar({ mapStr, referenceDate }: { mapStr: string; referenceDate: string | null }) {
  if (!mapStr) return <span>â€”</span>;
  const refDate = referenceDate ? new Date(referenceDate) : new Date();
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "4px", width: "fit-content" }}>
      {mapStr.split("").map((char, i) => {
        const isOk = char === "â–ˆ";
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

// â”€â”€ Info pill component â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

// â”€â”€ Equipment card component â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function EqCard({ eq, onDelete, onViewRecording, onEdit, onToggleActive }: {
  eq: NVR;
  onDelete: () => void;
  onViewRecording: () => void;
  onEdit: () => void;
  onToggleActive: () => void;
}) {
  const getEqIcon = (tipo: string) => {
    const m: any = {
      NVR: <Video size={18} />, OLT: <Wifi size={18} />, ONU: <WifiOff size={18} />, PABX: <Phone size={18} />, MIKROTIK: <Network size={18} />, DIGIFORT: <Video size={18} />
    };
    return m[tipo] || <Video size={18} />;
  };
  const getEqColor = (tipo: string) => {
    const m: any = {
      NVR: "var(--primary)", OLT: "#10b981", ONU: "#f59e0b", PABX: "#8b5cf6", MIKROTIK: "#3b82f6", DIGIFORT: "#f43f5e"
    };
    return m[tipo] || "var(--text-muted)";
  };
  const color = getEqColor(eq.tipo);

  return (
    <div style={{
      background: "var(--surface-2, rgba(255,255,255,0.03))",
      border: "1px solid var(--border)", borderRadius: "var(--radius)",
      padding: "16px 20px", display: "flex", alignItems: "center", gap: 16,
      transition: "border-color 0.15s", opacity: eq.active === false ? 0.6 : 1
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
        {getEqIcon(eq.tipo)}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: 14 }}>{eq.name}</span>
          <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: `${color}18`, color, border: `1px solid ${color}30` }}>
            {eq.tipo}
          </span>
          {eq.active === false && (
            <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: `var(--warn-bg)`, color: "var(--warn)", border: `1px solid rgba(245,158,11,0.3)` }}>
              PAUSADO
            </span>
          )}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 12 }}>
          {eq.tipo === "OLT" || eq.tipo === "DIGIFORT" ? (
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <FolderOpen size={12} /> {(eq.config_extra as any)?.pasta_origem || "â€”"}
            </span>
          ) : (
            <>
              <span style={{ fontFamily: "monospace" }}>{eq.ip}</span>
              {eq.username && <span style={{ display: "flex", alignItems: "center", gap: 3 }}>ðŸ‘¤ {eq.username}</span>}
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {(eq.tipo === "NVR" || eq.tipo === "DIGIFORT") && (
          <button className="btn btn-secondary btn-sm" onClick={onViewRecording}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Video size={13} /> GravaÃ§Ãµes
          </button>
        )}
        <button className="btn-icon" title={eq.active === false ? "Retomar Backup" : "Pausar Backup"} onClick={onToggleActive}>
          {eq.active === false ? <RefreshCw size={14} /> : <div style={{width:14, height:14, borderLeft:'3px solid currentColor', borderRight:'3px solid currentColor'}}/>}
        </button>
        <button className="btn-icon" title="Editar" onClick={onEdit}>
          <Edit2 size={14} />
        </button>
        <button className="btn-icon" style={{ color: "var(--err)" }} title="Remover" onClick={onDelete}>
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}

// â”€â”€ Main component â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export default function ClientDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [client, setClient] = useState<Client | null>(null);
  const [equipamentos, setEquipamentos] = useState<NVR[]>([]);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, {status: string, error?: string, image_base64?: string}>>({});


  const [showEqModal, setShowEqModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showRecordingModal, setShowRecordingModal] = useState<{ show: boolean, nvrName: string, cameras: any[] }>({ show: false, nvrName: "", cameras: [] });
  const [rotatedKey, setRotatedKey] = useState<string | null>(null);
  const [eqForm, setEqForm] = useState({ tipo: "NVR" as TipoEquipamento, name: "", ip: "", username: "", password: "", pasta_origem: "", fabricante_olt: "UNM2000" });
  const [editingEqId, setEditingEqId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<Client> & { zip_password?: string }>({});
  const [saving, setSaving] = useState(false);

  const TIPOS: TipoEquipamento[] = ["NVR", "OLT", "PABX", "MIKROTIK", "DIGIFORT", "DEFENSE"];
  const TIPO_ICONE_EMOJI: Record<string, string> = { NVR: "ðŸ“¹", OLT: "ðŸ”Œ", PABX: "ðŸ“ž", MIKROTIK: "ðŸŒ", DIGIFORT: "ðŸ–¥ï¸", DEFENSE: "ðŸ›¡ï¸" };

  const load = async (silent = false) => {
    if (!id) return;
    if (!silent) setLoading(true);
    const [c, eqs, b, lg] = await Promise.all([
      (await import("../api/client")).fetchClient(id),
      fetchEquipamentos(id),
      fetchBackups({ client_id: id, size: 10 }),
      (await import("../api/client")).fetchClientLogs(id),
    ]);
    setClient(c); setEquipamentos(eqs); setBackups(b.items); setLogs(lg);
    if (!silent) setLoading(false);
  };
  
  useEffect(() => { load(); }, [id]);

  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t1 = setInterval(() => setNow(Date.now()), 1000);
    const t2 = setInterval(() => { if (id) load(true); }, 10000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [id]);

const buildEqPayload = () => {
    if (!eqForm.name.trim()) return { error: "Preencha o nome do equipamento." };
    const payload: any = { tipo: eqForm.tipo, name: eqForm.name.trim(), ip: "", username: "", password: "", config_extra: null };

    if (eqForm.tipo === "NVR" || eqForm.tipo === "PABX" || eqForm.tipo === "MIKROTIK" || eqForm.tipo === "CAMERA") {
      if (eqForm.tipo === "CAMERA") payload.config_extra = { modelo: (eqForm as any).modelo || "Hikvision" };
      if (!eqForm.ip || (!editingEqId && (!eqForm.username || !eqForm.password))) return { error: `Para ${eqForm.tipo}, preencha IP/Host, usuÃ¡rio e senha.` };
      payload.ip = eqForm.ip.trim(); payload.username = eqForm.username.trim(); payload.password = eqForm.password;
    } else if (eqForm.tipo === "DIGIFORT") {
      if (!eqForm.pasta_origem) return { error: "Para DIGIFORT, informe a pasta de origem." };
      payload.ip = eqForm.pasta_origem.trim(); 
      payload.username = "digifort"; 
      payload.password = "digifort"; 
      payload.config_extra = { 
        pasta_origem: eqForm.pasta_origem.trim(),
        caminho_csv: (eqForm as any).caminho_csv?.trim() || "",
        caminho_log_csv: (eqForm as any).caminho_log_csv?.trim() || ""
      };
    } else if (eqForm.tipo === "OLT") {
      if (!eqForm.fabricante_olt) return { error: "Selecione o sistema da OLT." };
      payload.config_extra = { fabricante_olt: eqForm.fabricante_olt };
      if (eqForm.fabricante_olt === "UNM2000") {
        if (!eqForm.pasta_origem) return { error: "Para UNM2000, informe a pasta de origem dos backups." };
        payload.ip = eqForm.pasta_origem.trim(); payload.username = "unm2000"; payload.password = "unm2000"; payload.config_extra.pasta_origem = eqForm.pasta_origem.trim();
      } else if (eqForm.fabricante_olt === "HUAWEI" || eqForm.fabricante_olt === "VSOL") {
        if (!eqForm.ip || (!editingEqId && (!eqForm.username || !eqForm.password))) return { error: `Para ${eqForm.fabricante_olt}, preencha IP, usuÃ¡rio e senha.` };
        payload.ip = eqForm.ip.trim(); payload.username = eqForm.username.trim(); payload.password = eqForm.password;
        if (eqForm.fabricante_olt === "HUAWEI") payload.config_extra.pasta_origem = eqForm.pasta_origem.trim();
      }
    } else if (eqForm.tipo === "DEFENSE") {
      if (!eqForm.pasta_origem) return { error: "Para DEFENSE, informe a pasta de origem." };
      payload.ip = "127.0.0.1";
      payload.username = "defense";
      payload.password = "defense";
      payload.config_extra = {
        pasta_origem: eqForm.pasta_origem.trim()
      };
    }
    // Remove blank passwords in edit mode so backend ignores them
    if (editingEqId && !payload.password) delete payload.password;
    return { payload };
  };

  const handleSaveEquipamento = async () => {
    const { error, payload } = buildEqPayload();
    if (error) { toast(error, "error"); return; }
    
    setSaving(true);
    try {
      if (editingEqId) {
        await updateEquipamento(id!, editingEqId, payload);
        toast("Equipamento atualizado!", "success");
      } else {
        await createEquipamento(id!, payload);
        toast("Equipamento adicionado!", "success");
      }
      setShowEqModal(false);
      setEqForm({ tipo: "NVR", name: "", ip: "", username: "", password: "", pasta_origem: "", fabricante_olt: "UNM2000" });
      setEditingEqId(null);
      load();
    } catch { toast("Erro ao salvar equipamento.", "error"); }
    finally { setSaving(false); }
  };


  const handleToggleEquipamento = async (eq: NVR) => {
    try {
      const isCurrentlyActive = eq.active !== false; // true if true or undefined
      await updateEquipamento(id!, eq.id, { active: !isCurrentlyActive });
      toast(isCurrentlyActive ? "Equipamento pausado." : "Equipamento retomado.", "success");
      load();
    } catch { toast("Erro ao alterar estado.", "error"); }
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
    if (!confirm("Gerar nova API Key? A chave atual serÃ¡ invalidada.")) return;
    const data = await rotateKey(id!);
    setRotatedKey(data.api_key);
    load();
  };

  const handleRestartAgent = async () => {
    if (!confirm("Solicitar reinÃ­cio do agente? Ele serÃ¡ reiniciado no prÃ³ximo ping (atÃ© 5 min).")) return;
    try {
      await restartAgent(id!);
      toast("ReinÃ­cio agendado! O agente serÃ¡ reiniciado no prÃ³ximo ping.", "success");
    } catch { toast("Erro ao solicitar reinÃ­cio.", "error"); }
  };

  const handleTriggerBackup = async () => {
    if (!confirm("Solicitar execuÃ§Ã£o imediata de backup? Ele comeÃ§arÃ¡ no prÃ³ximo ping (atÃ© 5 min).")) return;
    try {
      await triggerBackup(id!);
      toast("Backup agendado! ComeÃ§arÃ¡ automaticamente no prÃ³ximo ping.", "success");
    } catch { toast("Erro ao solicitar backup.", "error"); }
  };

  const isAgentOnline = client && client.active &&
    (client.last_seen && new Date().getTime() - new Date(client.last_seen.endsWith("Z") ? client.last_seen : client.last_seen + "Z").getTime() < 15 * 60 * 1000);

  const copyText = (t: string) => { navigator.clipboard.writeText(t); toast("Copiado!", "success"); };

  if (loading) return <div className="loading-state"><div className="spinner" /></div>;
  if (!client) return <div className="empty-state">Cliente nÃ£o encontrado.</div>;

  let nextPingStr = "â€”";
  const isPendingAction = client.backup_requested || client.restart_requested;
  if (client.last_seen && isAgentOnline) {
    const lastSeenMs = new Date(client.last_seen.endsWith("Z") ? client.last_seen : client.last_seen + "Z").getTime();
    const nextPingMs = lastSeenMs + 5 * 60 * 1000;
    const diff = Math.max(0, nextPingMs - now);
    const mm = Math.floor(diff / 60000);
    const ss = Math.floor((diff % 60000) / 1000);
    nextPingStr = `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  }

  return (
    <>
      {/* â”€â”€ Header â”€â”€ */}
      <div className="page-header">
        <div className="flex items-center gap-3">
          <button className="btn-icon" onClick={() => navigate("/clients")} title="Voltar">
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="page-title">{client.name}</h1>
            <p className="page-subtitle flex items-center gap-2">
              <StatusBadge status={client.last_backup_status} />
              {client.last_backup_at && `Ãšltimo backup: ${fmtDate(client.last_backup_at)}`}
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
          <button className="btn btn-secondary" onClick={handleTriggerBackup}
            title={!isAgentOnline ? "Agente offline â€” o backup comeÃ§arÃ¡ no prÃ³ximo ping" : "Solicitar backup manual agora"}>
            <CloudLightning size={15} /> Gerar Backup
          </button>
          <button className="btn btn-secondary" onClick={handleRestartAgent}
            title={!isAgentOnline ? "Agente offline â€” o reinÃ­cio serÃ¡ executado no prÃ³ximo ping" : "Reiniciar o agente Windows"}>
            <RotateCcw size={15} /> Reiniciar Agent
          </button>
        </div>
      </div>

      {/* â”€â”€ Banner de Comando Pendente â”€â”€ */}
      {isPendingAction && (
        <div style={{ background: "rgba(245, 158, 11, 0.1)", border: "1px solid rgba(245, 158, 11, 0.3)", borderRadius: 6, padding: "12px 16px", marginBottom: 24, display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ color: "#f59e0b", display: "flex" }}><Clock size={18} /></div>
          <div style={{ fontSize: 13, color: "var(--text-primary)" }}>
            <strong>Comando na fila!</strong> O {client.backup_requested ? "backup manual" : "reinÃ­cio"} comeÃ§arÃ¡ no prÃ³ximo contato do agente 
            {isAgentOnline && <span style={{ fontWeight: 600, color: "#f59e0b", marginLeft: 6 }}>({nextPingStr})</span>}.
          </div>
        </div>
      )}

      {/* â”€â”€ Layout de duas colunas â”€â”€ */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>

        {/* Coluna 1 â€” ConfiguraÃ§Ã£o */}
        <div className="card" style={{ padding: "20px 24px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 16, display: "flex", alignItems: "center", gap: 6 }}>
            <Server size={13} /> ConfiguraÃ§Ã£o do Cliente
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <InfoPill icon={<KeyRound size={11} />} label="Client ID" value={client.id} mono copyValue={client.id} onCopy={copyText} />
            <InfoPill icon={<KeyRound size={11} />} label="API Key (prefixo)" value={`${client.api_key_prefix}â€¦`} mono />
            <InfoPill icon={<Clock size={11} />} label="HorÃ¡rio do Backup"
              value={`${String(client.backup_hour).padStart(2, "0")}:${String(client.backup_minute).padStart(2, "0")} (diÃ¡rio)`} />
            <InfoPill icon={<Mail size={11} />} label="E-mails de NotificaÃ§Ã£o"
              value={(client.email_to || []).join(", ") || "â€”"} />
          </div>
        </div>

        {/* Coluna 2 â€” Status */}
        <div className="card" style={{ padding: "20px 24px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 16, display: "flex", alignItems: "center", gap: 6 }}>
            <Wifi size={13} /> Status do Agente
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <InfoPill icon={<Wifi size={11} />} label="ConexÃ£o"
              value={<StatusBadge status={isAgentOnline ? "ONLINE" : (client.active ? "OFFLINE" : "DESATIVADO")} />} />
            <InfoPill icon={<CalendarCheck size={11} />} label="Ãšltimo contato"
              value={client.last_seen ? fmtDate(client.last_seen) : "Nunca"} />
            <InfoPill icon={<Clock size={11} />} label="PrÃ³ximo contato (estimado)"
              value={isAgentOnline ? nextPingStr : "â€”"} />
            <InfoPill icon={<Archive size={11} />} label="Ãšltimo Backup"
              value={<StatusBadge status={client.last_backup_status} />} />
            <InfoPill icon={<CalendarCheck size={11} />} label="Data do Ãšltimo Backup"
              value={fmtDate(client.last_backup_at)} />
          </div>
        </div>
      </div>

      {/* â”€â”€ Equipamentos â”€â”€ */}
      <div style={{ marginBottom: 24 }}>
        <div className="flex items-center justify-between mb-3">
          <div className="section-title mb-0">
            <Server size={15} /> Equipamentos
            <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
              {equipamentos.filter(e => e.tipo !== "CAMERA").length}
            </span>
          </div>
          <button className="btn btn-secondary" onClick={() => { setEditingEqId(null); setEqForm({ tipo: "NVR", name: "", ip: "", username: "", password: "", pasta_origem: "", fabricante_olt: "UNM2000" }); setShowEqModal(true); }}>
            <Plus size={14} /> Adicionar
          </button>
        </div>

        {equipamentos.filter(e => e.tipo !== "CAMERA").length === 0 ? (
          <div className="empty-state" style={{ padding: "32px" }}>
            <div className="empty-icon">ðŸ–¥ï¸</div>
            <div>Nenhum equipamento cadastrado.</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {equipamentos.filter(e => e.tipo !== "CAMERA").map(eq => (
              <EqCard key={eq.id} eq={eq}
                onDelete={() => handleDeleteEquipamento(eq.id, eq.name)}
                onViewRecording={() => setShowRecordingModal({ show: true, nvrName: eq.name, cameras: eq.last_recording_status || [] })}
                onEdit={() => {
                  setEditingEqId(eq.id);
                  setEqForm({
                    tipo: eq.tipo,
                    name: eq.name,
                    ip: eq.tipo === "DIGIFORT" || (eq.tipo === "OLT" && (eq.config_extra as any)?.fabricante_olt === "UNM2000") ? "" : eq.ip,
                    username: eq.username,
                    password: "", // do not fetch password
                    pasta_origem: (eq.config_extra as any)?.pasta_origem || (eq.tipo === "DIGIFORT" ? eq.ip : ""),
                    fabricante_olt: (eq.config_extra as any)?.fabricante_olt || "UNM2000",
                    caminho_csv: (eq.config_extra as any)?.caminho_csv || "",
                    caminho_log_csv: (eq.config_extra as any)?.caminho_log_csv || ""
                  } as any);
                  setShowEqModal(true);
                }}
                onToggleActive={() => handleToggleEquipamento(eq)}
              />
            ))}
          </div>
        )}
      </div>

      {/* â”€â”€ HistÃ³rico de Backups â”€â”€ */}
      <div>
        <div className="section-title">
          <Archive size={15} /> HistÃ³rico de Backups
          <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
            Ãºltimos 10
          </span>
        </div>
        {backups.length === 0 ? (
          <div className="empty-state" style={{ padding: "32px" }}>
            <div className="empty-icon">ðŸ“¦</div>
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
                  {b.zip_size ? `${(b.zip_size / 1024 / 1024).toFixed(1)} MB` : "â€”"}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }} title="E-mail enviado">
                  {b.email_sent ? "âœ… E-mail" : "â€”"}
                </div>
                <ChevronRight size={14} style={{ color: "var(--text-muted)", opacity: 0.4 }} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* â”€â”€ HistÃ³rico de Eventos do Agente â”€â”€ */}
      <div style={{ marginTop: 20 }}>
        <div className="section-title">
          <CloudLightning size={15} /> Eventos do Agente (Pings e InstruÃ§Ãµes)
          <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
            Ãºltimos {logs.length}
          </span>
        </div>
        {logs.length === 0 ? (
          <div className="empty-state" style={{ padding: "32px" }}>
            <div className="empty-icon">ðŸ“¡</div>
            <div>Nenhum evento registrado ainda. O agente deve enviar pings a cada 5 minutos.</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 300, overflowY: "auto", paddingRight: 8 }}>
            {logs.map((log: any) => (
              <div key={log.id} style={{
                display: "grid", gridTemplateColumns: "140px auto 1fr",
                alignItems: "center", gap: 12,
                background: "var(--surface-2, rgba(255,255,255,0.02))",
                border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                padding: "10px 16px"
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>
                  {fmtDate(log.created_at)}
                </div>
                <div style={{
                  fontSize: 10, fontWeight: 700, textTransform: "uppercase", padding: "2px 6px", borderRadius: 4,
                  background: log.event_type === "ping" ? "rgba(16, 185, 129, 0.15)" : "rgba(59, 130, 246, 0.15)",
                  color: log.event_type === "ping" ? "#10b981" : "#3b82f6"
                }}>
                  {log.event_type}
                </div>
                <div style={{ fontSize: 13, color: "var(--text-primary)" }}>
                  {log.message}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* â”€â”€ Modal: Adicionar Equipamento â”€â”€ */}
      {showEqModal && (
        <Modal title={editingEqId ? "Editar Equipamento" : "Adicionar Equipamento"} onClose={() => setShowEqModal(false)}>
          <div className="form-group">
            <label className="form-label">Tipo de Equipamento *</label>
            {eqForm.tipo === "CAMERA" ? (
              <div style={{ padding: "10px", background: "rgba(255,255,255,0.05)", borderRadius: 6, marginBottom: 16 }}>📷 Câmera RTSP</div>
            ) : (
            <select className="form-input" value={eqForm.tipo}
              onChange={e => setEqForm({ ...eqForm, tipo: e.target.value as TipoEquipamento, pasta_origem: e.target.value === "DEFENSE" ? "C:\\Intelbras Defense IA\\Intelbras Defense IA Server\\bak\\db_backup" : "", fabricante_olt: "UNM2000" })}>
              {TIPOS.map(t => <option key={t} value={t}>{TIPO_ICONE_EMOJI[t]} {t}</option>)}
            </select>
            )}
          </div>
          <div className="form-group">
            <label className="form-label">Nome *</label>
            <input className="form-input" type="text"
              placeholder={`${eqForm.tipo}_Cliente1`}
              value={eqForm.name} onChange={e => setEqForm({ ...eqForm, name: e.target.value })} />
          </div>
          {(eqForm.tipo === "NVR" || eqForm.tipo === "PABX" || eqForm.tipo === "MIKROTIK" || eqForm.tipo === "CAMERA") && (
            <>
              <div className="form-group">
                <label className="form-label">EndereÃ§o IP ou Host *</label>
                <input className="form-input" type="text" placeholder={eqForm.tipo === "PABX" ? "https://192.168.12.2" : "192.168.1.100"}
                  value={eqForm.ip} onChange={e => setEqForm({ ...eqForm, ip: e.target.value })} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">UsuÃ¡rio *</label>
                  <input className="form-input" type="text"
                    value={eqForm.username} onChange={e => setEqForm({ ...eqForm, username: e.target.value })} />
                </div>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">Senha {editingEqId ? <span style={{fontWeight:400, color:'var(--text-muted)'}}>(vazio = manter atual)</span> : '*'}</label>
                  <input className="form-input" type="password"
                    value={eqForm.password} onChange={e => setEqForm({ ...eqForm, password: e.target.value })} />
                </div>
              </div>

              {eqForm.tipo === "CAMERA" && (
                <div className="form-group" style={{ marginTop: 12 }}>
                  <label className="form-label">Modelo / Fabricante</label>
                  <select className="form-input" value={(eqForm as any).modelo || "Hikvision"} onChange={e => setEqForm({ ...eqForm, modelo: e.target.value } as any)}>
                    <option value="Hikvision">Hikvision / Outro</option>
                    <option value="Intelbras">Intelbras</option>
                    <option value="Grandstream">Grandstream</option>
                    <option value="ONVIF">ONVIF Genérico</option>
                  </select>
                </div>
              )}
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
                  <option value="UNM2000">ðŸ”µ UNM2000</option>
                  <option value="HUAWEI">ðŸ”´ HUAWEI</option>
                  <option value="VSOL">ðŸŸ¢ VSOL</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">
                  {(eqForm.fabricante_olt === "VSOL" || eqForm.fabricante_olt === "HUAWEI")
                    ? "EndereÃ§o IP da OLT *"
                    : "Pasta de Origem dos Backups *"}
                </label>

                <input
                  className="form-input"
                  type="text"
                  placeholder={
                    (eqForm.fabricante_olt === "VSOL" || eqForm.fabricante_olt === "HUAWEI")
                      ? "192.168.1.100"
                      : "C:\\Users\\Helena\\Documents"
                  }
                  value={
                    (eqForm.fabricante_olt === "VSOL" || eqForm.fabricante_olt === "HUAWEI") 
                      ? eqForm.ip 
                      : eqForm.pasta_origem
                  }
                  onChange={e => {
                    if (eqForm.fabricante_olt === "VSOL" || eqForm.fabricante_olt === "HUAWEI") {
                      setEqForm({ ...eqForm, ip: e.target.value })
                    } else {
                      setEqForm({ ...eqForm, pasta_origem: e.target.value })
                    }
                  }}
                />
              </div>

              {(eqForm.fabricante_olt === "VSOL" || eqForm.fabricante_olt === "HUAWEI") && (
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
                        UsuÃ¡rio *
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
                  {(eqForm.fabricante_olt === "UNM2000")
                    ? `Pasta onde o ${eqForm.fabricante_olt} exporta os arquivos de backup.`
                    : "EndereÃ§o IP, usuÃ¡rio e senha utilizados para acessar a OLT via SSH."
                  }
                </span>
            </>
          )}
          {eqForm.tipo === "DIGIFORT" && (
            <>
              <div className="form-group">
                <label className="form-label">Pasta de Origem do Digifort *</label>
                <input className="form-input" type="text"
                  placeholder="C:\Digifort\Backup"
                  value={eqForm.pasta_origem} onChange={e => setEqForm({ ...eqForm, pasta_origem: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Caminho do CSV Exportado (Opcional)</label>
                <input className="form-input" type="text"
                  placeholder="export_cameras.csv"
                  value={(eqForm as any).caminho_csv || ""} onChange={e => setEqForm({ ...eqForm, caminho_csv: e.target.value } as any)} />
                <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
                  Arquivo CSV com a descriÃ§Ã£o das cÃ¢meras gerado pelo Digifort.
                </span>
              </div>
              <div className="form-group">
                <label className="form-label">Caminho do LOG de GravaÃ§Ãµes (Opcional)</label>
                <input className="form-input" type="text"
                  placeholder="C:\...\quedas_cameras.csv"
                  value={(eqForm as any).caminho_log_csv || ""} onChange={e => setEqForm({ ...eqForm, caminho_log_csv: e.target.value } as any)} />
                <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
                  Arquivo CSV onde o Agente Webhook salva/lÃª o histÃ³rico (quedas_cameras.csv).
                </span>
              </div>
            </>
          )}
          {eqForm.tipo === "DEFENSE" && (
            <div className="form-group">
              <label className="form-label">Pasta de Origem do Backup *</label>
              <input className="form-input" type="text"
                placeholder="C:\Intelbras Defense IA\...\db_backup"
                value={eqForm.pasta_origem} onChange={e => setEqForm({ ...eqForm, pasta_origem: e.target.value })} />
              <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
                Pasta onde o Defense IA salva os arquivos gerados no backup automÃ¡tico.
              </span>
            </div>
          )}
          <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
            <button className="btn btn-secondary" onClick={() => setShowEqModal(false)}>Cancelar</button>
            <button className="btn btn-primary" onClick={handleSaveEquipamento} disabled={saving}>
              {saving ? <span className="spinner spinner-sm" /> : (editingEqId ? "Salvar" : <><Plus size={15} /> Adicionar</>)}
            </button>
          </div>
        </Modal>
      )}

      {/* â”€â”€ Modal: Editar Cliente â”€â”€ */}
      {showEditModal && (
        <Modal title="Editar Cliente" onClose={() => setShowEditModal(false)}>
          <div className="form-group">
            <label className="form-label">Nome</label>
            <input className="form-input" value={editForm.name || ""}
              onChange={e => setEditForm({ ...editForm, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">HorÃ¡rio do Backup AutomÃ¡tico</label>
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
            <label className="form-label">E-mails de NotificaÃ§Ã£o (separados por vÃ­rgula)</label>
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

      {/* â”€â”€ Modal: Nova API Key â”€â”€ */}
      {rotatedKey && (
        <Modal title="Nova API Key gerada" onClose={() => setRotatedKey(null)}>
          <div style={{
            background: "var(--warn-bg)", border: "1px solid rgba(245,158,11,0.3)",
            borderRadius: "var(--radius-sm)", padding: "12px 16px", marginBottom: 20,
            color: "var(--warn)", fontSize: 13
          }}>
            âš ï¸ Copie agora. NÃ£o serÃ¡ exibida novamente. Atualize o agent.conf no cliente.
          </div>
          <div className="api-key-display" style={{ borderColor: "rgba(245,158,11,0.4)" }}>
            <span className="api-key-value" style={{ color: "var(--warn)" }}>{rotatedKey}</span>
            <button className="btn-icon" onClick={() => copyText(rotatedKey)}><Copy size={14} /></button>
          </div>
          <button className="btn btn-primary mt-4 w-full" style={{ justifyContent: "center" }}
            onClick={() => setRotatedKey(null)}>Entendi</button>
        </Modal>
      )}

      {/* â”€â”€ Modal: Status de GravaÃ§Ã£o â”€â”€ */}
      {showRecordingModal.show && (
        <Modal wide={true} title={`GravaÃ§Ã£o â€” ${showRecordingModal.nvrName} (${fmtDate(client.last_backup_at)})`}
          onClose={() => setShowRecordingModal({ show: false, nvrName: "", cameras: [] })}>
          {showRecordingModal.cameras.length === 0 ? (
            <div className="empty-state">Sem dados de gravaÃ§Ã£o disponÃ­veis.</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>CÃ¢mera</th>
                    <th>Rede</th>
                    <th>GravaÃ§Ã£o</th>
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
                      const gravouHoje = cam.mapa ? cam.mapa.endsWith("â–ˆ") : cam.total_dias > 0;
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
