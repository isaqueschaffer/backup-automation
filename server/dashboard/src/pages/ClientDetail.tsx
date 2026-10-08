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
import {
  ArrowLeft, Plus, Trash2, RefreshCw, Copy, Edit2, Server,
  Archive, RotateCcw, Clock, Mail, CalendarCheck, KeyRound,
  Wifi, WifiOff, Video, FolderOpen, ChevronRight, Phone, Network, CloudLightning, Image
} from "lucide-react";

function fmtDate(s: string | null) {
  if (!s) return "—";
  const str = s.endsWith("Z") ? s : s + "Z";
  return new Date(str).toLocaleString("pt-BR");
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

// ── NVR Cameras Modal ──────────────────────────────────────────────
function NVRCamerasGalleryModal({ clientId, nvrId, nvrName, onClose }: { clientId: string, nvrId: string, nvrName: string, onClose: () => void }) {
  const [cameras, setCameras] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [zoomImage, setZoomImage] = useState<{ src: string, title: string } | null>(null);

  useEffect(() => {
    const fetchCams = async () => {
      setLoading(true);
      try {
        const res = await api.get(`/clients/${clientId}/equipamentos/${nvrId}/cameras`);
        setCameras(res.data);
      } catch (e) {
        console.error("Error fetching cameras:", e);
      }
      setLoading(false);
    };
    fetchCams();
  }, [clientId, nvrId]);

  const [testingCanal, setTestingCanal] = useState<number | null>(null);

  const capturePerfectImage = async (canal: number, nome: string) => {
    setTestingCanal(canal);
    try {
      // 1. Testa RTSP pelo agente
      const resRtsp = await api.post(`/clients/${clientId}/equipamentos/${nvrId}/test-rtsp?canal=${canal}`);
      const dataRtsp = resRtsp.data;
      if (!dataRtsp.success || !dataRtsp.image_base64) {
        alert(dataRtsp.error_message || "Falha ao capturar imagem. Verifique se o Agente está online.");
        setTestingCanal(null);
        return;
      }
      
      // 2. Salva a imagem
      const resSave = await api.post(`/clients/${clientId}/equipamentos/${nvrId}/cameras/perfect-image`, {
        canal, nome, image_base64: dataRtsp.image_base64
      });
      const savedCam = resSave.data;
      setCameras(prev => prev.map(c => c.canal === canal ? { ...c, perfect_image_base64: savedCam.perfect_image_base64 } : c));
    } catch (e: any) {
      alert(e.response?.data?.detail || "Erro ao comunicar com o servidor.");
    }
    setTestingCanal(null);
  };

  return (
    <>
      <Modal title={`Câmeras do NVR: ${nvrName}`} onClose={onClose} width="900px">
        {loading ? (
          <div style={{ padding: 40, textAlign: "center" }}>Carregando galeria...</div>
        ) : cameras.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>Nenhuma câmera sincronizada neste NVR ainda. Aguarde o próximo backup.</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {cameras.map(cam => (
              <div key={cam.id} className="card" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontWeight: 600, borderBottom: "1px solid var(--border)", paddingBottom: 8, marginBottom: 4 }}>
                  {cam.nome || `Canal ${cam.canal}`}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 4 }}>PERFECT IMAGE (DIA)</div>
                    {cam.perfect_image_base64 ? (
                      <img 
                        src={`data:image/jpeg;base64,${cam.perfect_image_base64}`} 
                        alt="Perfect" 
                        style={{ width: "100%", borderRadius: 4, aspectRatio: "16/9", objectFit: "cover", marginBottom: 8, cursor: "zoom-in", transition: "transform 0.2s" }} 
                        onMouseOver={(e) => (e.currentTarget.style.transform = "scale(1.02)")}
                        onMouseOut={(e) => (e.currentTarget.style.transform = "scale(1)")}
                        onClick={() => setZoomImage({ src: `data:image/jpeg;base64,${cam.perfect_image_base64}`, title: `${cam.nome || `Canal ${cam.canal}`} - PERFECT IMAGE` })}
                      />
                    ) : (
                      <div style={{ width: "100%", aspectRatio: "16/9", background: "var(--surface-2)", display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 4, fontSize: 11, color: "var(--text-muted)", border: "1px dashed var(--border)", marginBottom: 8 }}>Sem imagem</div>
                    )}
                    <button className="btn btn-secondary btn-sm" style={{ marginTop: "auto", fontSize: 11, width: "100%", justifyContent: "center" }} onClick={() => capturePerfectImage(cam.canal, cam.nome)} disabled={testingCanal === cam.canal}>
                      {testingCanal === cam.canal ? "Capturando..." : "Capturar Imagem Perfeita"}
                    </button>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 4 }}>ÚLTIMO BACKUP (NOITE)</div>
                    {cam.night_image_base64 ? (
                      <img 
                        src={`data:image/jpeg;base64,${cam.night_image_base64}`} 
                        alt="Night" 
                        style={{ width: "100%", borderRadius: 4, aspectRatio: "16/9", objectFit: "cover", cursor: "zoom-in", transition: "transform 0.2s" }} 
                        onMouseOver={(e) => (e.currentTarget.style.transform = "scale(1.02)")}
                        onMouseOut={(e) => (e.currentTarget.style.transform = "scale(1)")}
                        onClick={() => setZoomImage({ src: `data:image/jpeg;base64,${cam.night_image_base64}`, title: `${cam.nome || `Canal ${cam.canal}`} - ÚLTIMO BACKUP` })}
                      />
                    ) : (
                      <div style={{ width: "100%", aspectRatio: "16/9", background: "var(--surface-2)", display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 4, fontSize: 11, color: "var(--text-muted)", border: "1px dashed var(--border)" }}>Sem imagem</div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Modal>

      {zoomImage && (
        <div 
          style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.85)", zIndex: 999999, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", cursor: "zoom-out", padding: 40 }}
          onClick={() => setZoomImage(null)}
        >
          <div style={{ color: "white", fontSize: 18, fontWeight: 600, marginBottom: 16 }}>{zoomImage.title}</div>
          <img src={zoomImage.src} style={{ maxWidth: "100%", maxHeight: "85vh", objectFit: "contain", borderRadius: 8, boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)" }} />
          <div style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 16 }}>Clique em qualquer lugar para fechar</div>
        </div>
      )}
    </>
  );
}

// ── Equipment card component ─────────────────────────────────────
function EqCard({ eq, onDelete, onViewRecording, onViewCameras, onEdit, onToggleActive }: {
  eq: NVR;
  onDelete: () => void;
  onViewRecording: () => void;
  onViewCameras?: () => void;
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
        {eq.tipo === "NVR" && onViewCameras && (
          <button className="btn btn-secondary btn-sm" onClick={onViewCameras}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Image size={13} /> Galeria
          </button>
        )}
        {(eq.tipo === "NVR" || eq.tipo === "DIGIFORT") && (
          <button className="btn btn-secondary btn-sm" onClick={onViewRecording}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Video size={13} /> Gravações
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

// ── Main component ───────────────────────────────────────────────
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
  const [showNVRCamerasModal, setShowNVRCamerasModal] = useState<{ show: boolean, nvrId: string, nvrName: string }>({ show: false, nvrId: "", nvrName: "" });
  const [rotatedKey, setRotatedKey] = useState<string | null>(null);
  const [eqForm, setEqForm] = useState({ tipo: "NVR" as TipoEquipamento, name: "", ip: "", username: "", password: "", pasta_origem: "", fabricante_olt: "UNM2000" });
  const [editingEqId, setEditingEqId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<Client> & { zip_password?: string }>({});
  const [saving, setSaving] = useState(false);

  const TIPOS: TipoEquipamento[] = ["NVR", "OLT", "PABX", "MIKROTIK", "DIGIFORT", "DEFENSE"];
  const TIPO_ICONE_EMOJI: Record<string, string> = { NVR: "📹", OLT: "🔌", PABX: "📞", MIKROTIK: "🌐", DIGIFORT: "🖥️", DEFENSE: "🛡️" };

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
      if (!eqForm.ip || (!editingEqId && (!eqForm.username || !eqForm.password))) return { error: `Para ${eqForm.tipo}, preencha IP/Host, usuário e senha.` };
      payload.ip = eqForm.ip.trim(); payload.username = eqForm.username.trim(); payload.password = eqForm.password;
      if (eqForm.tipo === "CAMERA") {
        payload.config_extra = { modelo: (eqForm as any).modelo || "Hikvision" };
      } else if (eqForm.tipo === "NVR") {
        payload.config_extra = { marca: (eqForm as any).marca || "Hikvision" };
      }
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
        if (!eqForm.ip || (!editingEqId && (!eqForm.username || !eqForm.password))) return { error: `Para ${eqForm.fabricante_olt}, preencha IP, usuário e senha.` };
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

  const handleTriggerBackup = async () => {
    if (!confirm("Solicitar execução imediata de backup? Ele começará no próximo ping (até 5 min).")) return;
    try {
      await triggerBackup(id!);
      toast("Backup agendado! Começará automaticamente no próximo ping.", "success");
    } catch { toast("Erro ao solicitar backup.", "error"); }
  };

  const isAgentOnline = client && client.active &&
    (client.last_seen && new Date().getTime() - new Date(client.last_seen.endsWith("Z") ? client.last_seen : client.last_seen + "Z").getTime() < 15 * 60 * 1000);

  const copyText = (t: string) => { navigator.clipboard.writeText(t); toast("Copiado!", "success"); };

  if (loading) return <div className="loading-state"><div className="spinner" /></div>;
  if (!client) return <div className="empty-state">Cliente não encontrado.</div>;

  let nextPingStr = "—";
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
          <button className="btn btn-secondary" onClick={handleTriggerBackup}
            title={!isAgentOnline ? "Agente offline — o backup começará no próximo ping" : "Solicitar backup manual agora"}>
            <CloudLightning size={15} /> Gerar Backup
          </button>
          <button className="btn btn-secondary" onClick={handleRestartAgent}
            title={!isAgentOnline ? "Agente offline — o reinício será executado no próximo ping" : "Reiniciar o agente Windows"}>
            <RotateCcw size={15} /> Reiniciar Agent
          </button>
        </div>
      </div>

      {/* ── Banner de Comando Pendente ── */}
      {isPendingAction && (
        <div style={{ background: "rgba(245, 158, 11, 0.1)", border: "1px solid rgba(245, 158, 11, 0.3)", borderRadius: 6, padding: "12px 16px", marginBottom: 24, display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ color: "#f59e0b", display: "flex" }}><Clock size={18} /></div>
          <div style={{ fontSize: 13, color: "var(--text-primary)" }}>
            <strong>Comando na fila!</strong> O {client.backup_requested ? "backup manual" : "reinício"} começará no próximo contato do agente 
            {isAgentOnline && <span style={{ fontWeight: 600, color: "#f59e0b", marginLeft: 6 }}>({nextPingStr})</span>}.
          </div>
        </div>
      )}

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
            <InfoPill icon={<Clock size={11} />} label="Próximo contato (estimado)"
              value={isAgentOnline ? nextPingStr : "—"} />
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
              {equipamentos.filter(e => e.tipo !== "CAMERA").length}
            </span>
          </div>
          <button className="btn btn-secondary" onClick={() => { setEditingEqId(null); setEqForm({ tipo: "NVR", name: "", ip: "", username: "", password: "", pasta_origem: "", fabricante_olt: "UNM2000" } as any); setShowEqModal(true); }}>
            <Plus size={14} /> Adicionar
          </button>
        </div>

        {equipamentos.filter(e => e.tipo !== "CAMERA").length === 0 ? (
          <div className="empty-state" style={{ padding: "32px" }}>
            <div className="empty-icon">🖥️</div>
            <div>Nenhum equipamento cadastrado.</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {equipamentos.filter(e => e.tipo !== "CAMERA").map(eq => (
              <EqCard key={eq.id} eq={eq}
                onDelete={() => handleDeleteEquipamento(eq.id, eq.name)}
                onViewRecording={() => setShowRecordingModal({ show: true, nvrName: eq.name, cameras: eq.last_recording_status || [] })}
                onViewCameras={() => setShowNVRCamerasModal({ show: true, nvrId: eq.id, nvrName: eq.name })}
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
                    caminho_log_csv: (eq.config_extra as any)?.caminho_log_csv || "",
                    marca: (eq.config_extra as any)?.marca || "Hikvision"
                  } as any);
                  setShowEqModal(true);
                }}
                onToggleActive={() => handleToggleEquipamento(eq)}
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

      
      {/* ── Câmeras (Teste RTSP) ── */}
      <div style={{ marginBottom: 24, marginTop: 24 }}>
        <div className="flex items-center justify-between mb-4">
          <div className="section-title mb-0">
            <Video size={15} /> Câmeras do Cliente (Teste RTSP)
            <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
              {equipamentos.filter(e => e.tipo === "CAMERA").length}
            </span>
          </div>
          <div className="flex gap-2">
            <input type="file" accept=".csv" ref={fileInputRef} style={{ display: 'none' }} onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const reader = new FileReader();
              reader.onload = async (evt) => {
                const text = evt.target?.result as string;
                const lines = text.split("\n");
                let count = 0;
                setLoading(true);
                try {
                  for (let i = 1; i < lines.length; i++) {
                    const line = lines[i].trim();
                    if (!line) continue;
                    const cols = line.split(";").map(c => c.replace(/^"|"$/g, "").trim());
                    const desc = cols[1] || "";
                    const mod = cols[2] || "Hikvision";
                    const ender = cols[3] || "";
                    const pass = cols[6] || "";

                    if (desc && ender) {
                      await api.post(`/clients/${id}/equipamentos`, {
                        tipo: "CAMERA",
                        name: desc,
                        ip: ender,
                        username: "admin",
                        password: pass,
                        config_extra: { modelo: mod }
                      });
                      count++;
                    }
                  }
                  toast(`Importadas ${count} câmeras com sucesso!`, "success");
                  load();
                } catch (err) {
                  toast("Erro ao importar câmeras.", "error");
                } finally {
                  setLoading(false);
                  if (fileInputRef.current) fileInputRef.current.value = '';
                }
              };
              reader.readAsText(file, "ISO-8859-1");
            }} />
            <button className="btn btn-secondary" onClick={() => fileInputRef.current?.click()} disabled={loading || isTesting}>
              <Plus size={14} /> Importar CSV
            </button>
            <button className="btn btn-secondary" onClick={() => { setEditingEqId(null); setEqForm({ tipo: "CAMERA", name: "", ip: "", username: "admin", password: "navarro@123", modelo: "Hikvision" } as any); setShowEqModal(true); }}>
              <Plus size={14} /> Adicionar Câmera
            </button>
            <button className="btn btn-secondary" disabled={Object.values(testResults).filter(r => r.image_base64).length === 0} onClick={async () => {
              const successCams = Object.entries(testResults).filter(([_, res]) => res.image_base64);
              if (successCams.length === 1) {
                const [camId, res] = successCams[0];
                const cam = equipamentos.find(e => e.id === camId);
                const name = cam ? cam.name.replace(/\s+/g, '_') : camId;
                const a = document.createElement("a");
                a.href = `data:image/jpeg;base64,${res.image_base64}`;
                a.download = `camera_${name}.jpg`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
              } else if (successCams.length > 1) {
                const JSZip = (await import("jszip")).default;
                const zip = new JSZip();
                successCams.forEach(([camId, res]) => {
                  const cam = equipamentos.find(e => e.id === camId);
                  const name = cam ? cam.name.replace(/\s+/g, '_') : camId;
                  zip.file(`camera_${name}.jpg`, res.image_base64!, { base64: true });
                });
                const blob = await zip.generateAsync({ type: "blob" });
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = `cameras_${client?.name?.replace(/\\s+/g, '_') || 'cliente'}.zip`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
              }
            }}>
              Baixar Imagens
            </button>
            <button className="btn btn-success" disabled={loading || isTesting || equipamentos.filter(e => e.tipo === "CAMERA").length === 0} onClick={async () => {
              const cams = equipamentos.filter(e => e.tipo === "CAMERA");
              if (cams.length === 0) return;
              setIsTesting(true);
              setTestResults({});
              
              for (const cam of cams) {
                setTestResults(prev => ({ ...prev, [cam.id]: { status: "testing" } }));
                try {
                  const res = await api.post(`/clients/${id}/equipamentos/${cam.id}/test-rtsp`);
                  if (res.data.success) {
                    setTestResults(prev => ({ ...prev, [cam.id]: { status: "success", image_base64: res.data.image_base64 } }));
                  } else {
                    setTestResults(prev => ({ ...prev, [cam.id]: { status: "error", error: res.data.error_message } }));
                  }
                } catch (err: any) {
                  setTestResults(prev => ({ ...prev, [cam.id]: { status: "error", error: "Erro de comunicação na API." } }));
                }
              }
              setIsTesting(false);
              toast("Teste RTSP concluído!", "success");
            }}>
              {isTesting ? "Testando..." : "Testar Todas"}
            </button>
          </div>
        </div>

        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border)', textAlign: 'left', background: 'var(--surface-2)' }}>
                <th style={{ padding: '12px 16px' }}>Descrição</th>
                <th style={{ padding: '12px 16px' }}>IP</th>
                <th style={{ padding: '12px 16px' }}>Modelo</th>
                <th style={{ padding: '12px 16px' }}>Status RTSP</th>
                <th style={{ padding: '12px 16px' }}>Preview</th>
                <th style={{ padding: '12px 16px', textAlign: 'right' }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {equipamentos.filter(e => e.tipo === "CAMERA").map(cam => {
                const res = testResults[cam.id];
                return (
                  <tr key={cam.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '12px 16px' }}>{cam.name}</td>
                    <td style={{ padding: '12px 16px', fontFamily: 'monospace' }}>{cam.ip}</td>
                    <td style={{ padding: '12px 16px' }}>{(cam.config_extra as any)?.modelo || "N/A"}</td>
                    <td style={{ padding: '12px 16px' }}>
                      {!res && <span style={{ color: '#888' }}>⏳ Aguardando</span>}
                      {res?.status === "testing" && <span style={{ color: '#d97706' }}>🔄 Testando...</span>}
                      {res?.status === "success" && <span style={{ color: '#16a34a', fontWeight: 'bold' }}>✅ Sucesso</span>}
                      {res?.status === "error" && (
                        <div>
                          <span style={{ color: '#dc2626', fontWeight: 'bold' }}>❌ Erro</span>
                          <div style={{ fontSize: '0.8rem', color: '#dc2626', marginTop: 4 }}>{res.error}</div>
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {res?.image_base64 && (
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                          <img src={`data:image/jpeg;base64,${res.image_base64}`} alt="Preview" style={{ maxHeight: '60px', borderRadius: '4px', border: '1px solid #ccc' }} />
                          <a href={`data:image/jpeg;base64,${res.image_base64}`} download={`camera_${cam.name.replace(/\\s+/g, '_')}.jpg`} title="Baixar Imagem" style={{ cursor: 'pointer', background: 'var(--surface-2)', padding: '6px', borderRadius: '4px', border: '1px solid var(--border)', textDecoration: 'none' }}>
                            📥
                          </a>
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: 12, marginRight: 8 }} onClick={() => {
                        setEditingEqId(cam.id);
                        setEqForm({
                          tipo: "CAMERA",
                          name: cam.name,
                          ip: cam.ip,
                          username: cam.username,
                          password: "",
                          modelo: (cam.config_extra as any)?.modelo || "Hikvision"
                        } as any);
                        setShowEqModal(true);
                      }}>Editar</button>
                      <button onClick={() => handleDeleteEquipamento(cam.id, cam.name)} disabled={isTesting} style={{ background: 'none', border: 'none', color: '#dc2626', cursor: 'pointer', fontSize: 12 }}>Remover</button>
                    </td>
                  </tr>
                );
              })}
              {equipamentos.filter(e => e.tipo === "CAMERA").length === 0 && (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)' }}>Nenhuma câmera cadastrada. Use "Importar CSV" ou adicione manualmente.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Histórico de Eventos do Agente ── */}
      <div style={{ marginTop: 20 }}>
        <div className="section-title">
          <CloudLightning size={15} /> Eventos do Agente (Pings e Instruções)
          <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
            últimos {logs.length}
          </span>
        </div>
        {logs.length === 0 ? (
          <div className="empty-state" style={{ padding: "32px" }}>
            <div className="empty-icon">📡</div>
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

      {/* ── Modal: Adicionar Equipamento ── */}
      {showEqModal && (
        <Modal title={editingEqId ? "Editar Equipamento" : "Adicionar Equipamento"} onClose={() => setShowEqModal(false)}>
          <div className="form-group">
            <label className="form-label">Tipo de Equipamento *</label>
            {eqForm.tipo === "CAMERA" as any ? (
              <div style={{ padding: "10px", background: "rgba(255,255,255,0.05)", borderRadius: 6, marginBottom: 16 }}>📷 Câmera (RTSP)</div>
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
              {eqForm.tipo === "NVR" && (
                <div className="form-group" style={{ marginTop: 12 }}>
                  <label className="form-label">Marca do NVR</label>
                  <select className="form-input" value={(eqForm as any).marca || "Hikvision"} onChange={e => setEqForm({ ...eqForm, marca: e.target.value } as any)}>
                    <option value="Hikvision">Hikvision / Intelbras / Outros</option>
                    <option value="Motorola">Motorola</option>
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
                  <option value="UNM2000">🔵 UNM2000</option>
                  <option value="HUAWEI">🔴 HUAWEI</option>
                  <option value="VSOL">🟢 VSOL</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">
                  {(eqForm.fabricante_olt === "VSOL" || eqForm.fabricante_olt === "HUAWEI")
                    ? "Endereço IP da OLT *"
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
                  {(eqForm.fabricante_olt === "UNM2000")
                    ? `Pasta onde o ${eqForm.fabricante_olt} exporta os arquivos de backup.`
                    : "Endereço IP, usuário e senha utilizados para acessar a OLT via SSH."
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
                  Arquivo CSV com a descrição das câmeras gerado pelo Digifort.
                </span>
              </div>
              <div className="form-group">
                <label className="form-label">Caminho do LOG de Gravações (Opcional)</label>
                <input className="form-input" type="text"
                  placeholder="C:\...\quedas_cameras.csv"
                  value={(eqForm as any).caminho_log_csv || ""} onChange={e => setEqForm({ ...eqForm, caminho_log_csv: e.target.value } as any)} />
                <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
                  Arquivo CSV onde o Agente Webhook salva/lê o histórico (quedas_cameras.csv).
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
                Pasta onde o Defense IA salva os arquivos gerados no backup automático.
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

      {/* ── NVR Cameras Gallery Modal ── */}
      {showNVRCamerasModal.show && (
        <NVRCamerasGalleryModal
          clientId={id!}
          nvrId={showNVRCamerasModal.nvrId}
          nvrName={showNVRCamerasModal.nvrName}
          onClose={() => setShowNVRCamerasModal({ show: false, nvrId: "", nvrName: "" })}
        />
      )}
    </>
  );
}
