import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  fetchCustomer, fetchMachine, fetchMachineLogs, fetchEquipamentos, createEquipamento, updateEquipamento,
  deleteEquipamento, updateMachine, rotateMachineKey, fetchBackups, restartMachineAgent, triggerMachineBackup
} from "../../../api/client";
import { AgentLog, Backup, CameraRecStatus, Machine, EqForm, NVR, NVRTelemetry, TipoEquipamento } from "../../../api/types";
import { useToast } from "../../../components/Toast";
import { apiErrorMessage } from "../../../utils/errors";
import { ChevronDown, ChevronRight, Plus, Server } from "lucide-react";
import {
  AGENT_PING_INTERVAL_MS, OVERDUE_FAST_POLL_MS, serverUtcMs,
  buildEqPayload, emptyEqForm, eqToForm, parseEmails
} from "./utils";
import { useCameraImport } from "./hooks/useCameraImport";
import { useRtspTest } from "./hooks/useRtspTest";
import MachineHeader from "./components/MachineHeader";
import MachineInfoCards from "./components/MachineInfoCards";
import EqCard from "./components/EqCard";
import { EQ_TIPO_ORDEM, eqCor, eqIcone, eqRotulo } from "./components/eqTipos";
import BackupHistory from "./components/BackupHistory";
import CamerasSection from "./components/CamerasSection";
import AgentLogs from "./components/AgentLogs";
import EquipamentoFormModal from "./components/EquipamentoFormModal";
import EditMachineModal, { EditMachineForm } from "./components/EditMachineModal";
import RotatedKeyModal from "./components/RotatedKeyModal";
import RecordingModal from "./components/RecordingModal";
import NVRCamerasGalleryModal from "./components/NVRCamerasGalleryModal";
import NVRTelemetryModal from "./components/NVRTelemetryModal";
import ImportCamerasModal from "./components/ImportCamerasModal";
import { useSomenteLeitura } from "../../../contexts/AuthContext";

export default function MachineDetail() {
  const somenteLeitura = useSomenteLeitura();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [machine, setMachine] = useState<Machine | null>(null);
  const [equipamentos, setEquipamentos] = useState<NVR[]>([]);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [gruposAbertos, setGruposAbertos] = useState<Set<string>>(new Set());

  const [mostrarPings, setMostrarPings] = useState(false);
  const mostrarPingsRef = useRef(false);

  const [showEqModal, setShowEqModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showRecordingModal, setShowRecordingModal] = useState<{ show: boolean, nvrName: string, cameras: CameraRecStatus[] }>({ show: false, nvrName: "", cameras: [] });
  const [showNVRCamerasModal, setShowNVRCamerasModal] = useState<{ show: boolean, nvrId: string, nvrName: string, eqTipo: TipoEquipamento }>({ show: false, nvrId: "", nvrName: "", eqTipo: "NVR" });
  const [showTelemetryModal, setShowTelemetryModal] = useState<{ show: boolean, nvrName: string, telemetry: NVRTelemetry | null | undefined }>({ show: false, nvrName: "", telemetry: null });
  const [rotatedKey, setRotatedKey] = useState<string | null>(null);
  const [eqForm, setEqForm] = useState<EqForm>(emptyEqForm());
  const [editingEqId, setEditingEqId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditMachineForm>({
    name: "", backup_hour: 2, backup_minute: 0, email_to: "", zip_password: "",
  });
  const [saving, setSaving] = useState(false);
  // E-mails efetivos quando vêm do cliente (null = ainda não carregados ou máquina sem cliente)
  const [customerEmails, setCustomerEmails] = useState<string[] | null>(null);
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
      const [m, eqs, b, lg] = await Promise.all([
        fetchMachine(reqId),
        fetchEquipamentos(reqId),
        fetchBackups({ machine_id: reqId, size: 10 }),
        fetchMachineLogs(reqId, mostrarPingsRef.current),
      ]);
      if (!isCurrent()) return;
      setMachine(m); setEquipamentos(eqs); setBackups(b.items); setLogs(lg);
      if (m.current_server_time) setServerSkewMs(new Date(m.current_server_time).getTime() - Date.now());
    } catch (e) {
      // Polling (silent) falha em silêncio; carga explícita avisa o usuário
      if (!silent && isCurrent()) {
        console.error(e);
        toast("Erro ao carregar dados da máquina.", "error");
      }
    } finally {
      if (!silent && isCurrent()) setLoading(false);
    }
  }, [id, toast]);

  const handleTogglePings = (v: boolean) => {
    mostrarPingsRef.current = v;
    setMostrarPings(v);
    load(true);
  };

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

  // Busca os e-mails do cliente só quando muda o vínculo (não a cada polling)
  const emailCustomerId = machine?.email_from_customer ? machine.customer_id ?? null : null;
  useEffect(() => {
    setCustomerEmails(null);
    if (!emailCustomerId) return;
    let cancelled = false;
    fetchCustomer(emailCustomerId)
      .then(c => { if (!cancelled) setCustomerEmails(c.email_to || []); })
      .catch(() => { /* mantém null: o card mostra os e-mails da máquina */ });
    return () => { cancelled = true; };
  }, [emailCustomerId]);

  const nextPingMs = machine?.last_seen && machine.active && machine.is_online
    ? serverUtcMs(machine.last_seen) + AGENT_PING_INTERVAL_MS
    : null;
  const overdueMs = nextPingMs === null ? -1 : now + serverSkewMs - nextPingMs;
  const fastPoll = overdueMs >= 0 && overdueMs < OVERDUE_FAST_POLL_MS;
  useEffect(() => {
    if (!fastPoll || !id) return;
    let cancelled = false;
    const t = setInterval(async () => {
      try {
        const c = await fetchMachine(id);
        if (cancelled) return;
        setMachine(c);
        if (c.current_server_time) setServerSkewMs(new Date(c.current_server_time).getTime() - Date.now());
      } catch { /* próxima tentativa em 1s */ }
    }, 1000);
    return () => { cancelled = true; clearInterval(t); };
  }, [fastPoll, id]);

  const cameras = equipamentos.filter(e => e.tipo === "CAMERA");
  const otherEquipamentos = equipamentos.filter(e => e.tipo !== "CAMERA");

  const gruposEquipamentos = (() => {
    const porTipo = new Map<string, NVR[]>();
    for (const eq of otherEquipamentos) {
      const lista = porTipo.get(eq.tipo) ?? [];
      lista.push(eq);
      porTipo.set(eq.tipo, lista);
    }
    const posicao = (t: string) => { const i = EQ_TIPO_ORDEM.indexOf(t); return i === -1 ? EQ_TIPO_ORDEM.length : i; };
    return [...porTipo.entries()]
      .sort((a, b) => posicao(a[0]) - posicao(b[0]) || a[0].localeCompare(b[0]))
      .map(([tipo, itens]) => ({ tipo, itens: [...itens].sort((a, b) => a.name.localeCompare(b.name, "pt-BR", { numeric: true })) }));
  })();

  const alternarGrupo = (tipo: string) => setGruposAbertos(prev => {
    const prox = new Set(prev);
    if (prox.has(tipo)) prox.delete(tipo); else prox.add(tipo);
    return prox;
  });

  const {
    fileInputRef, importFile, deleteAll,
    modalImport, mudarOpcaoNome, cancelarImportacao, confirmarImportacao,
  } = useCameraImport({
    machineId: id, cameras, setBusy: setLoading, reload: load, toast,
  });
  const { isTesting, testResults, hasImages, testAll, downloadImages } = useRtspTest({
    machineId: id, equipamentos, machineName: machine?.name, toast,
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
      load(true);
    } catch { toast("Erro ao salvar equipamento.", "error"); }
    finally { setSaving(false); }
  };

  const handleToggleEquipamento = async (eq: NVR) => {
    try {
      const isCurrentlyActive = eq.active !== false; // true if true or undefined
      await updateEquipamento(id!, eq.id, { active: !isCurrentlyActive });
      toast(isCurrentlyActive ? "Equipamento pausado." : "Equipamento retomado.", "success");
      load(true);
    } catch { toast("Erro ao alterar estado.", "error"); }
  };

  const handleDeleteEquipamento = async (eqId: string, name: string) => {
    if (!confirm(`Remover equipamento "${name}"?`)) return;
    try {
      await deleteEquipamento(id!, eqId);
      toast("Equipamento removido.", "success");
      load(true);
    } catch { toast("Erro ao remover equipamento.", "error"); }
  };

  const openEditMachine = () => {
    if (!machine) return;
    setEditForm({
      name: machine.name,
      backup_hour: machine.backup_hour,
      backup_minute: machine.backup_minute,
      email_to: ((machine.email_from_customer && customerEmails) || machine.email_to || []).join(", "),
      zip_password: "",
    });
    setShowEditModal(true);
  };

  const handleEditSave = async () => {
    setSaving(true);
    try {
      // Só os campos editáveis. Cliente e posição na fila mudam na tela do Cliente;
      // com cliente, o horário vem dele e não é enviado.
      // Idem para os e-mails: com cliente, vêm dele e não são enviados.
      const payload: Record<string, unknown> = {
        name: editForm.name,
        zip_password: editForm.zip_password || undefined,
      };
      if (!machine?.email_from_customer) payload.email_to = parseEmails(editForm.email_to);
      if (!machine?.schedule_from_customer) {
        payload.backup_hour = editForm.backup_hour;
        payload.backup_minute = editForm.backup_minute;
      }
      await updateMachine(id!, payload);
      toast("Máquina atualizada!", "success");
      setShowEditModal(false);
      load(true);
    } catch (e) { toast(apiErrorMessage(e, "Erro ao salvar a máquina."), "error"); }
    finally { setSaving(false); }
  };

  const handleRotateKey = async () => {
    if (!confirm("Gerar nova API Key? A chave atual será invalidada.")) return;
    try {
      const data = await rotateMachineKey(id!);
      setRotatedKey(data.api_key || null);
      load(true);
    } catch { toast("Erro ao gerar nova API Key.", "error"); }
  };

  const handleRestartAgent = async () => {
    if (!confirm("Solicitar reinício do agente? Ele será reiniciado no próximo ping (em poucos segundos se estiver online).")) return;
    try {
      await restartMachineAgent(id!);
      toast("Reinício agendado! O agente será reiniciado no próximo ping.", "success");
    } catch { toast("Erro ao solicitar reinício.", "error"); }
  };

  const handleTriggerBackup = async () => {
    if (!confirm("Solicitar execução imediata de backup? Ele começará no próximo ping (em poucos segundos se estiver online).")) return;
    try {
      await triggerMachineBackup(id!);
      toast("Backup agendado! Começará automaticamente no próximo ping.", "success");
    } catch { toast("Erro ao solicitar backup.", "error"); }
  };

  // is_online calculado no servidor — elimina bugs de fuso horário no navegador
  const isAgentOnline = !!(machine && machine.active && machine.is_online);

  const copyText = (t: string) => {
    navigator.clipboard.writeText(t).then(
      () => toast("Copiado!", "success"),
      () => toast("Não foi possível copiar.", "error"),
    );
  };

  if (loading) return <div className="loading-state"><div className="spinner" /></div>;
  if (!machine) return <div className="empty-state">Máquina não encontrada.</div>;

  let nextPingStr = "—";
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
      <MachineHeader
        machine={machine} isAgentOnline={isAgentOnline} nextPingStr={nextPingStr}
        onBack={() => navigate(machine.customer_id ? `/clientes/${machine.customer_id}` : "/maquinas")} onEdit={openEditMachine} onRotateKey={handleRotateKey}
        onTriggerBackup={handleTriggerBackup} onRestartAgent={handleRestartAgent}
      />

      {/* ── Layout de três colunas ── */}
      <MachineInfoCards machine={machine} customerEmails={customerEmails} isAgentOnline={isAgentOnline} nextPingStr={nextPingStr} onCopy={copyText} nowMs={now + serverSkewMs} />

      {/* ── Equipamentos ── */}
      <div style={{ marginBottom: 24 }}>
        <div className="flex items-center justify-between mb-3">
          <div className="section-title mb-0">
            <Server size={15} /> Equipamentos
            <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
              {otherEquipamentos.length}
            </span>
          </div>
          {!somenteLeitura && (
            <button className="btn btn-secondary" onClick={() => openEqModal(emptyEqForm(), null)}>
              <Plus size={14} /> Adicionar
            </button>
          )}
        </div>

        {otherEquipamentos.length === 0 ? (
          <div className="empty-state" style={{ padding: "32px" }}>
            <div className="empty-icon">🖥️</div>
            <div>Nenhum equipamento cadastrado.</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {gruposEquipamentos.map(g => {
              const aberto = gruposAbertos.has(g.tipo);
              return (
                <div key={g.tipo}>
                  <button
                    type="button"
                    onClick={() => alternarGrupo(g.tipo)}
                    aria-expanded={aberto}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      marginBottom: aberto ? 8 : 0,
                      color: eqCor(g.tipo),
                      fontSize: 12,
                      fontWeight: 700,
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      background: "none",
                      border: "none",
                      padding: "4px 0",
                      cursor: "pointer",
                      width: "100%",
                      textAlign: "left",
                    }}
                  >
                    {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    {eqIcone(g.tipo, 14)} {eqRotulo(g.tipo)}
                    <span style={{ fontSize: 11, fontWeight: 600, padding: "1px 7px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>{g.itens.length}</span>
                  </button>
                  {aberto && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {g.itens.map(eq => (
                        <EqCard key={eq.id} eq={eq}
                          somenteLeitura={somenteLeitura}
                          onDelete={() => handleDeleteEquipamento(eq.id, eq.name)}
                          onViewRecording={() => setShowRecordingModal({ show: true, nvrName: eq.name, cameras: eq.last_recording_status || [] })}
                          onViewCameras={() => setShowNVRCamerasModal({ show: true, nvrId: eq.id, nvrName: eq.name, eqTipo: eq.tipo })}
                          onViewTelemetry={() => setShowTelemetryModal({ show: true, nvrName: eq.name, telemetry: eq.last_telemetry_status })}
                          onEdit={() => openEqModal(eqToForm(eq), eq.id)}
                          onToggleActive={() => handleToggleEquipamento(eq)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
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
      <AgentLogs
        logs={logs}
        mostrarPings={mostrarPings}
        onTogglePings={handleTogglePings}
        lastSeen={machine?.last_seen ?? null}
        online={machine?.is_online}
      />

      {/* ── Modal: Adicionar/Editar Equipamento ── */}
      {showEqModal && (
        <EquipamentoFormModal
          eqForm={eqForm} setEqForm={setEqForm} editingEqId={editingEqId}
          saving={saving} onSave={handleSaveEquipamento} onClose={() => setShowEqModal(false)}
        />
      )}

      {/* ── Modal: Editar Máquina ── */}
      {showEditModal && (
        <EditMachineModal
          form={editForm} setForm={setEditForm}
          customerName={machine.schedule_from_customer ? (machine.customer_name || "vinculado") : null}
          emailCustomerName={machine.email_from_customer ? (machine.customer_name || "vinculado") : null}
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
          lastBackupAt={machine.last_backup_at}
          onClose={() => setShowRecordingModal({ show: false, nvrName: "", cameras: [] })}
        />
      )}

      {/* ── NVR Cameras Gallery Modal ── */}
      {showNVRCamerasModal.show && (
        <NVRCamerasGalleryModal
          machineId={id!}
          nvrId={showNVRCamerasModal.nvrId}
          nvrName={showNVRCamerasModal.nvrName}
          eqTipo={showNVRCamerasModal.eqTipo}
          onClose={() => setShowNVRCamerasModal({ show: false, nvrId: "", nvrName: "", eqTipo: "NVR" })}
        />
      )}

      {/* ── NVR Telemetry Modal ── */}
      {showTelemetryModal.show && (
        <NVRTelemetryModal
          nvrName={showTelemetryModal.nvrName}
          telemetry={showTelemetryModal.telemetry}
          onClose={() => setShowTelemetryModal({ show: false, nvrName: "", telemetry: null })}
        />
      )}

      {/* ── Modal: Importar Câmeras da Planilha (Teste RTSP) ── */}
      {modalImport && (
        <ImportCamerasModal
          fileName={modalImport.fileName}
          cameras={modalImport.cameras}
          totalLinhas={modalImport.rows.length}
          temOpcaoNomeDescricao={modalImport.temOpcaoNomeDescricao}
          opcaoNome={modalImport.opcaoNome}
          onMudarOpcaoNome={mudarOpcaoNome}
          exemploNome={modalImport.exemploNome}
          exemploDescricao={modalImport.exemploDescricao}
          onConfirmar={confirmarImportacao}
          onClose={cancelarImportacao}
        />
      )}
    </>
  );
}
