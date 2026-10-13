import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchGroups, createGroup, deleteGroup,
  triggerGroupBackup, downloadGroupZip, updateGroup
} from "../api/client";
import { ClientGroup } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import Modal from "../components/Modal";
import { useToast } from "../components/Toast";
import {
  Plus, Trash2, Eye, ChevronDown, ChevronRight,
  CloudLightning, Download, Building2, Edit2, Clock
} from "lucide-react";

function healthLabel(health: ClientGroup["health"]) {
  const map: Record<string, { label: string; color: string; bg: string }> = {
    ALL_OK: { label: "Tudo OK", color: "var(--ok)", bg: "rgba(16,185,129,0.12)" },
    PARTIAL: { label: "Parcial", color: "var(--warn)", bg: "var(--warn-bg)" },
    ALL_ERROR: { label: "Crítico", color: "var(--err)", bg: "var(--err-bg)" },
    NO_DATA: { label: "Sem dados", color: "var(--text-muted)", bg: "rgba(255,255,255,0.05)" },
  };
  return map[health] || map.NO_DATA;
}

function fmtDate(s: string | null) {
  if (!s) return "—";
  const str = s.endsWith("Z") ? s : s + "Z";
  return new Date(str).toLocaleString("pt-BR");
}

interface GroupForm {
  name: string;
  description: string;
  backup_hour: number;
  backup_minute: number;
}

export default function Units() {
  const [groups, setGroups] = useState<ClientGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState<ClientGroup | null>(null);
  const [form, setForm] = useState<GroupForm>({ name: "", description: "", backup_hour: 2, backup_minute: 0 });
  const [editForm, setEditForm] = useState<GroupForm>({ name: "", description: "", backup_hour: 2, backup_minute: 0 });
  const [saving, setSaving] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  const load = () => fetchGroups().then(setGroups).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const toggleExpand = (id: string) =>
    setExpandedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const handleCreate = async () => {
    if (!form.name.trim()) { toast("Nome obrigatório.", "error"); return; }
    setSaving(true);
    try {
      await createGroup({ name: form.name, description: form.description || undefined, backup_hour: form.backup_hour, backup_minute: form.backup_minute, active: true });
      toast("Unidade criada!", "success");
      setShowCreate(false);
      setForm({ name: "", description: "", backup_hour: 2, backup_minute: 0 });
      load();
    } catch { toast("Erro ao criar unidade.", "error"); }
    finally { setSaving(false); }
  };

  const handleEdit = async () => {
    if (!showEdit) return;
    if (!editForm.name.trim()) { toast("Nome obrigatório.", "error"); return; }
    setSaving(true);
    try {
      await updateGroup(showEdit.id, { name: editForm.name, description: editForm.description || undefined, backup_hour: editForm.backup_hour, backup_minute: editForm.backup_minute });
      toast("Unidade atualizada!", "success");
      setShowEdit(null);
      load();
    } catch { toast("Erro ao atualizar unidade.", "error"); }
    finally { setSaving(false); }
  };

  const handleDelete = async (g: ClientGroup) => {
    if (!confirm(`Excluir unidade "${g.name}"? Os agentes vinculados ficarão sem unidade.`)) return;
    await deleteGroup(g.id);
    toast("Unidade removida.", "success");
    load();
  };

  const handleTriggerBackup = async (g: ClientGroup) => {
    if (!confirm(`Iniciar fila de backup para todos os ${g.agents_total} agente(s) de "${g.name}"?`)) return;
    setTriggeringId(g.id);
    try {
      await triggerGroupBackup(g.id);
      toast(`Fila iniciada! ${g.agents_total} agente(s) em sequência.`, "success");
      load();
    } catch (e: any) {
      toast(e?.response?.data?.detail || "Erro ao disparar backup.", "error");
    } finally { setTriggeringId(null); }
  };

  const handleDownload = async (g: ClientGroup) => {
    setDownloadingId(g.id);
    try {
      await downloadGroupZip(g.id, g.name);
      toast("Download iniciado!", "success");
    } catch (e: any) {
      toast(e?.message || "Erro ao baixar ZIP.", "error");
    } finally { setDownloadingId(null); }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Unidades</h1>
          <p className="page-subtitle">{groups.length} unidade(s) — grupos de agentes por local/empresa</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <Plus size={15} /> Nova Unidade
        </button>
      </div>

      {loading ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : groups.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🏢</div>
          <div>Nenhuma unidade cadastrada.</div>
          <button className="btn btn-primary mt-2" onClick={() => setShowCreate(true)}>Criar agora</button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {groups.map(g => {
            const expanded = expandedIds.has(g.id);
            const h = healthLabel(g.health);
            return (
              <div key={g.id} style={{
                background: "var(--surface-2, rgba(255,255,255,0.03))",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                overflow: "hidden",
              }}>
                {/* Cabeçalho do grupo */}
                <div
                  style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 16, cursor: "pointer", background: expanded ? "rgba(255,255,255,0.02)" : "transparent" }}
                  onClick={() => toggleExpand(g.id)}
                >
                  <div style={{ color: "var(--text-muted)", flexShrink: 0 }}>
                    {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </div>
                  <div style={{ width: 40, height: 40, borderRadius: "var(--radius-sm)", background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.3)", display: "flex", alignItems: "center", justifyContent: "center", color: "#6366f1", flexShrink: 0 }}>
                    <Building2 size={18} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 700, fontSize: 15, color: "var(--text-primary)" }}>{g.name}</span>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 10px", borderRadius: 999, background: h.bg, color: h.color, border: `1px solid ${h.color}40` }}>{h.label}</span>
                      {g.queue_active && (
                        <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 10px", borderRadius: 999, background: "rgba(245,158,11,0.12)", color: "var(--warn)", border: "1px solid rgba(245,158,11,0.3)" }}>
                          ⏳ Fila em andamento
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
                      <span>
                        <span style={{ fontWeight: 600, color: g.agents_online > 0 ? "var(--ok)" : "var(--err)" }}>{g.agents_online}/{g.agents_total}</span>{" "}agente{g.agents_total !== 1 ? "s" : ""} online
                      </span>
                      <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <Clock size={11} />{String(g.backup_hour).padStart(2, "0")}:{String(g.backup_minute).padStart(2, "0")} diário
                      </span>
                      {g.last_backup_at && <span>Último backup: {fmtDate(g.last_backup_at)}</span>}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
                    <button className="btn btn-secondary btn-sm" title="Iniciar fila de backup" disabled={triggeringId === g.id || g.queue_active} onClick={() => handleTriggerBackup(g)} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {triggeringId === g.id ? <span className="spinner spinner-sm" /> : <CloudLightning size={13} />}
                      Backup
                    </button>
                    <button className="btn btn-secondary btn-sm" title="Baixar ZIP agrupado" disabled={downloadingId === g.id} onClick={() => handleDownload(g)} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {downloadingId === g.id ? <span className="spinner spinner-sm" /> : <Download size={13} />}
                      ZIP
                    </button>
                    <button className="btn-icon" title="Editar" onClick={() => { setEditForm({ name: g.name, description: g.description || "", backup_hour: g.backup_hour, backup_minute: g.backup_minute }); setShowEdit(g); }}>
                      <Edit2 size={14} />
                    </button>
                    <button className="btn-icon" style={{ color: "var(--err)" }} title="Excluir" onClick={() => handleDelete(g)}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {/* Lista de agentes (accordion) */}
                {expanded && (
                  <div style={{ borderTop: "1px solid var(--border)", background: "rgba(0,0,0,0.15)" }}>
                    {g.clients.length === 0 ? (
                      <div style={{ padding: "20px 24px", color: "var(--text-muted)", fontSize: 13, display: "flex", alignItems: "center", gap: 12 }}>
                        <span>Nenhum agente vinculado.</span>
                        <button className="btn btn-secondary btn-sm" onClick={() => navigate("/clients")}>Vincular em Clientes</button>
                      </div>
                    ) : (
                      [...g.clients]
                        .sort((a, b) => (a.queue_order ?? 0) - (b.queue_order ?? 0))
                        .map((client, idx) => (
                          <div key={client.id} style={{ padding: "12px 24px 12px 76px", display: "flex", alignItems: "center", gap: 16, borderBottom: idx < g.clients.length - 1 ? "1px solid var(--border)" : "none" }}>
                            <div style={{ width: 24, height: 24, borderRadius: "50%", background: "rgba(255,255,255,0.06)", border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "var(--text-muted)", flexShrink: 0 }}>{idx + 1}</div>
                            <div style={{ width: 8, height: 8, borderRadius: "50%", flexShrink: 0, background: !client.active ? "var(--text-muted)" : client.is_online ? "var(--ok)" : "var(--err)", boxShadow: client.is_online && client.active ? "0 0 6px var(--ok)" : "none" }} />
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)" }}>{client.name}</div>
                              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                                {client.nvr_count} equipamento{client.nvr_count !== 1 ? "s" : ""}{client.last_backup_at && ` • Backup: ${fmtDate(client.last_backup_at)}`}
                              </div>
                            </div>
                            <StatusBadge status={client.last_backup_status} />
                            <button className="btn-icon" title="Ver detalhes" onClick={() => navigate(`/clients/${client.id}`)}><Eye size={14} /></button>
                          </div>
                        ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Modal criar */}
      {showCreate && (
        <Modal title="Nova Unidade" onClose={() => setShowCreate(false)}>
          <div className="form-group">
            <label className="form-label">Nome *</label>
            <input className="form-input" placeholder="Ex: Supermercado Central" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">Descrição (opcional)</label>
            <input className="form-input" placeholder="Ex: Filial centro" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="flex gap-3">
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Hora do backup (BRT)</label>
              <input className="form-input" type="number" min={0} max={23} value={form.backup_hour} onChange={e => setForm({ ...form, backup_hour: +e.target.value })} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Minuto</label>
              <input className="form-input" type="number" min={0} max={59} value={form.backup_minute} onChange={e => setForm({ ...form, backup_minute: +e.target.value })} />
            </div>
          </div>
          <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
            <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancelar</button>
            <button className="btn btn-primary" onClick={handleCreate} disabled={saving}>
              {saving ? <span className="spinner spinner-sm" /> : <><Plus size={15} /> Criar</>}
            </button>
          </div>
        </Modal>
      )}

      {/* Modal editar */}
      {showEdit && (
        <Modal title={`Editar: ${showEdit.name}`} onClose={() => setShowEdit(null)}>
          <div className="form-group">
            <label className="form-label">Nome *</label>
            <input className="form-input" value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">Descrição (opcional)</label>
            <input className="form-input" value={editForm.description} onChange={e => setEditForm({ ...editForm, description: e.target.value })} />
          </div>
          <div className="flex gap-3">
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Hora do backup (BRT)</label>
              <input className="form-input" type="number" min={0} max={23} value={editForm.backup_hour} onChange={e => setEditForm({ ...editForm, backup_hour: +e.target.value })} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Minuto</label>
              <input className="form-input" type="number" min={0} max={59} value={editForm.backup_minute} onChange={e => setEditForm({ ...editForm, backup_minute: +e.target.value })} />
            </div>
          </div>
          <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
            <button className="btn btn-secondary" onClick={() => setShowEdit(null)}>Cancelar</button>
            <button className="btn btn-primary" onClick={handleEdit} disabled={saving}>
              {saving ? <span className="spinner spinner-sm" /> : <><Edit2 size={15} /> Salvar</>}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
