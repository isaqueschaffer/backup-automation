import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  fetchClient, fetchClientLogs, fetchGroups, fetchEquipamentos, createEquipamento, updateEquipamento,
  deleteEquipamento, updateClient, rotateKey, fetchBackups, restartAgent, triggerBackup
} from "../../api/client";
import { AgentLog, Backup, CameraRecStatus, Client, ClientGroup, EqForm, NVR } from "../../api/types";
import StatusBadge from "../../components/StatusBadge";
import { useToast } from "../../components/Toast";
import { fmtDate } from "../../utils/date";
import {
  ArrowLeft, Plus, RefreshCw, Edit2, Server, RotateCcw, Clock, CloudLightning
} from "lucide-react";
import {
  AGENT_PING_INTERVAL_MS, OVERDUE_FAST_POLL_MS, serverUtcMs,
  buildEqPayload, emptyEqForm, eqToForm, parseEmails
} from "./utils";
import { useCameraImport } from "./hooks/useCameraImport";
import { useRtspTest } from "./hooks/useRtspTest";
import ClientInfoCards from "./components/ClientInfoCards";
import EqCard from "./components/EqCard";
import BackupHistory from "./components/BackupHistory";
import CamerasSection from "./components/CamerasSection";
import AgentLogs from "./components/AgentLogs";
import EquipamentoFormModal from "./components/EquipamentoFormModal";
import EditClientModal, { EditClientForm } from "./components/EditClientModal";
import RotatedKeyModal from "./components/RotatedKeyModal";
import RecordingModal from "./components/RecordingModal";
import NVRCamerasGalleryModal from "./components/NVRCamerasGalleryModal";

export default function ClientDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [client, setClient] = useState<Client | null>(null);
  const [equipamentos, setEquipamentos] = useState<NVR[]>([]);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [loading, setLoading] = useState(true);

  const [showEqModal, setShowEqModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showRecordingModal, setShowRecordingModal] = useState<{ show: boolean, nvrName: string, cameras: CameraRecStatus[] }>({ show: false, nvrName: "", cameras: [] });
  const [showNVRCamerasModal, setShowNVRCamerasModal] = useState<{ show: boolean, nvrId: string, nvrName: string }>({ show: false, nvrId: "", nvrName: "" });
  const [rotatedKey, setRotatedKey] = useState<string | null>(null);
  const [eqForm, setEqForm] = useState<EqForm>(emptyEqForm());
  const [editingEqId, setEditingEqId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditClientForm>({
    name: "", backup_hour: 2, backup_minute: 0, group_id: "", queue_order: 0, email_to: "", zip_password: "",
  });
  const [saving, setSaving] = useState(false);
  const [groups, setGroups] = useState<ClientGroup[]>([]);
  // Diferença entre relógio do servidor e do navegador, para a contagem do próximo ping andar a cada segundo
  const [serverSkewMs, setServerSkewMs] = useState(0);

  // Id atualmente exibido: respostas de requisições de outro id (ou após desmontar) são descartadas
  const activeIdRef = useRef<string | undefined>(undefined);

  const load = useCallback(async (silent = false) => {
    if (!id) return;
    const reqId = id;
    const isCurrent = () => activeIdRef.current === reqId;
    if (!silent) setLoading(true);
    try {
      const [c, eqs, b, lg, gs] = await Promise.all([
        fetchClient(reqId),
        fetchEquipamentos(reqId),
        fetchBackups({ client_id: reqId, size: 10 }),
        fetchClientLogs(reqId),
        fetchGroups().catch((): ClientGroup[] => []),
      ]);
      if (!isCurrent()) return;
      setClient(c); setEquipamentos(eqs); setBackups(b.items); setLogs(lg); setGroups(gs);
      if (c.current_server_time) setServerSkewMs(new Date(c.current_server_time).getTime() - Date.now());
    } catch (e) {
      // Polling (silent) falha em silêncio; carga explícita avisa o usuário
      if (!silent && isCurrent()) {
        console.error(e);
        toast("Erro ao carregar dados do cliente.", "error");
      }
    } finally {
      if (!silent && isCurrent()) setLoading(false);
    }
  }, [id, toast]);

  useEffect(() => {
    activeIdRef.current = id;
    load();
    return () => { activeIdRef.current = undefined; };
  }, [id, load]);

  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t1 = setInterval(() => setNow(Date.now()), 1000);
    const t2 = setInterval(() => { if (id) load(true); }, 10000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [id, load]);

  const nextPingMs = client?.last_seen && client.active && client.is_online
    ? serverUtcMs(client.last_seen) + AGENT_PING_INTERVAL_MS
    : null;
  const overdueMs = nextPingMs === null ? -1 : now + serverSkewMs - nextPingMs;
  const fastPoll = overdueMs >= 0 && overdueMs < OVERDUE_FAST_POLL_MS;
  useEffect(() => {
    if (!fastPoll || !id) return;
    let cancelled = false;
    const t = setInterval(async () => {
      try {
        const c = await fetchClient(id);
        if (cancelled) return;
        setClient(c);
        if (c.current_server_time) setServerSkewMs(new Date(c.current_server_time).getTime() - Date.now());
      } catch { /* próxima tentativa em 1s */ }
    }, 1000);
    return () => { cancelled = true; clearInterval(t); };
  }, [fastPoll, id]);

  const cameras = equipamentos.filter(e => e.tipo === "CAMERA");
  const otherEquipamentos = equipamentos.filter(e => e.tipo !== "CAMERA");

  const { fileInputRef, importFile, deleteAll } = useCameraImport({
    clientId: id, cameras, setBusy: setLoading, reload: load, toast,
  });
  const { isTesting, testResults, hasImages, testAll, downloadImages } = useRtspTest({
    clientId: id, equipamentos, clientName: client?.name, toast,
  });

  const openEqModal = (form: EqForm, eqId: string | null) => {
    setEditingEqId(eqId);
    setEqForm(form);
    setShowEqModal(true);
  };

  const handleSaveEquipamento = async () => {
    const { error, payload } = buildEqPayload(eqForm, editingEqId);
    if (error || !payload) { toast(error || "Dados inválidos.", "error"); return; }

    setSaving(true);
    try {
      if (editingEqId) {
        await updateEquipamento(id!, editingEqId, { ...payload });
        toast("Equipamento atualizado!", "success");
      } else {
        await createEquipamento(id!, { ...payload });
        toast("Equipamento adicionado!", "success");
      }
      setShowEqModal(false);
      setEqForm(emptyEqForm());
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
    try {
      await deleteEquipamento(id!, eqId);
      toast("Equipamento removido.", "success");
      load();
    } catch { toast("Erro ao remover equipamento.", "error"); }
  };

  const openEditClient = () => {
    if (!client) return;
    setEditForm({
      name: client.name,
      backup_hour: client.backup_hour,
      backup_minute: client.backup_minute,
      group_id: client.group_id || "",
      queue_order: client.queue_order ?? 0,
      email_to: (client.email_to || []).join(", "),
      zip_password: "",
    });
    setShowEditModal(true);
  };

  const handleEditSave = async () => {
    setSaving(true);
    try {
      // Só os campos editáveis; group_id apenas quando houver grupo selecionado
      // (o backend rejeita group_id vazio com 422).
      const payload: Record<string, unknown> = {
        name: editForm.name,
        backup_hour: editForm.backup_hour,
        backup_minute: editForm.backup_minute,
        email_to: parseEmails(editForm.email_to),
        zip_password: editForm.zip_password || undefined,
        queue_order: editForm.queue_order,
      };
      if (editForm.group_id) payload.group_id = editForm.group_id;
      await updateClient(id!, payload);
      toast("Cliente atualizado!", "success");
      setShowEditModal(false);
      load();
    } catch { toast("Erro ao salvar.", "error"); }
    finally { setSaving(false); }
  };

  const handleRotateKey = async () => {
    if (!confirm("Gerar nova API Key? A chave atual será invalidada.")) return;
    try {
      const data = await rotateKey(id!);
      setRotatedKey(data.api_key);
      load();
    } catch { toast("Erro ao gerar nova API Key.", "error"); }
  };

  const handleRestartAgent = async () => {
    if (!confirm("Solicitar reinício do agente? Ele será reiniciado no próximo ping (em poucos segundos se estiver online).")) return;
    try {
      await restartAgent(id!);
      toast("Reinício agendado! O agente será reiniciado no próximo ping.", "success");
    } catch { toast("Erro ao solicitar reinício.", "error"); }
  };

  const handleTriggerBackup = async () => {
    if (!confirm("Solicitar execução imediata de backup? Ele começará no próximo ping (em poucos segundos se estiver online).")) return;
    try {
      await triggerBackup(id!);
      toast("Backup agendado! Começará automaticamente no próximo ping.", "success");
    } catch { toast("Erro ao solicitar backup.", "error"); }
  };

  // is_online calculado no servidor — elimina bugs de fuso horário no navegador
  const isAgentOnline = !!(client && client.active && client.is_online);

  const copyText = (t: string) => {
    navigator.clipboard.writeText(t).then(
      () => toast("Copiado!", "success"),
      () => toast("Não foi possível copiar.", "error"),
    );
  };

  if (loading) return <div className="loading-state"><div className="spinner" /></div>;
  if (!client) return <div className="empty-state">Cliente não encontrado.</div>;

  let nextPingStr = "—";
  const isPendingAction = client.backup_requested || client.restart_requested;
  if (nextPingMs !== null) {
    if (overdueMs >= 0) {
      nextPingStr = "aguardando…";
    } else {
      const secs = Math.ceil(-overdueMs / 1000);
      nextPingStr = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
    }
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
          <button className="btn btn-secondary" onClick={openEditClient}>
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

      {/* ── Layout de três colunas ── */}
      <ClientInfoCards client={client} isAgentOnline={isAgentOnline} nextPingStr={nextPingStr} onCopy={copyText} />

      {/* ── Equipamentos ── */}
      <div style={{ marginBottom: 24 }}>
        <div className="flex items-center justify-between mb-3">
          <div className="section-title mb-0">
            <Server size={15} /> Equipamentos
            <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
              {otherEquipamentos.length}
            </span>
          </div>
          <button className="btn btn-secondary" onClick={() => openEqModal(emptyEqForm(), null)}>
            <Plus size={14} /> Adicionar
          </button>
        </div>

        {otherEquipamentos.length === 0 ? (
          <div className="empty-state" style={{ padding: "32px" }}>
            <div className="empty-icon">🖥️</div>
            <div>Nenhum equipamento cadastrado.</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {otherEquipamentos.map(eq => (
              <EqCard key={eq.id} eq={eq}
                onDelete={() => handleDeleteEquipamento(eq.id, eq.name)}
                onViewRecording={() => setShowRecordingModal({ show: true, nvrName: eq.name, cameras: eq.last_recording_status || [] })}
                onViewCameras={() => setShowNVRCamerasModal({ show: true, nvrId: eq.id, nvrName: eq.name })}
                onEdit={() => openEqModal(eqToForm(eq), eq.id)}
                onToggleActive={() => handleToggleEquipamento(eq)}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Histórico de Backups ── */}
      <BackupHistory backups={backups} />

      {/* ── Câmeras (Teste RTSP) ── */}
      <CamerasSection
        cameras={cameras}
        testResults={testResults}
        isTesting={isTesting}
        loading={loading}
        hasImages={hasImages}
        fileInputRef={fileInputRef}
        onImportFile={importFile}
        onImportClick={() => fileInputRef.current?.click()}
        onDeleteAll={deleteAll}
        onAdd={() => openEqModal(emptyEqForm({ tipo: "CAMERA", username: "admin", password: "navarro@123", modelo: "Hikvision" }), null)}
        onEdit={cam => openEqModal(emptyEqForm({
          tipo: "CAMERA", name: cam.name, ip: cam.ip, username: cam.username, password: "",
          modelo: cam.config_extra?.modelo || "Hikvision",
        }), cam.id)}
        onRemove={cam => handleDeleteEquipamento(cam.id, cam.name)}
        onDownloadImages={downloadImages}
        onTestAll={testAll}
      />

      {/* ── Histórico de Eventos do Agente ── */}
      <AgentLogs logs={logs} />

      {/* ── Modal: Adicionar/Editar Equipamento ── */}
      {showEqModal && (
        <EquipamentoFormModal
          eqForm={eqForm} setEqForm={setEqForm} editingEqId={editingEqId}
          saving={saving} onSave={handleSaveEquipamento} onClose={() => setShowEqModal(false)}
        />
      )}

      {/* ── Modal: Editar Cliente ── */}
      {showEditModal && (
        <EditClientModal
          form={editForm} setForm={setEditForm} groups={groups}
          saving={saving} onSave={handleEditSave} onClose={() => setShowEditModal(false)}
        />
      )}

      {/* ── Modal: Nova API Key ── */}
      {rotatedKey && (
        <RotatedKeyModal apiKey={rotatedKey} onCopy={copyText} onClose={() => setRotatedKey(null)} />
      )}

      {/* ── Modal: Status de Gravação ── */}
      {showRecordingModal.show && (
        <RecordingModal
          nvrName={showRecordingModal.nvrName}
          cameras={showRecordingModal.cameras}
          lastBackupAt={client.last_backup_at}
          onClose={() => setShowRecordingModal({ show: false, nvrName: "", cameras: [] })}
        />
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
