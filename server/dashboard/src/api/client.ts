/// <reference types="vite/client" />
import axios from "axios";
import { ClientGroup } from "./types";

const API_BASE = import.meta.env.VITE_API_URL || "";

const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("trilan_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Redirect to login on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("trilan_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────
export const login = (password: string) =>
  api.post("/auth/login", { password }).then((r) => r.data);

// ── Stats ─────────────────────────────────────────────────────
export const fetchStats = () => api.get("/stats").then((r) => r.data);

// ── Machines (Máquinas / Agentes) ───────────────────────────
export const fetchClients = () => api.get("/machines").then((r) => r.data);
export const fetchClient = (id: string) => api.get(`/machines/${id}`).then((r) => r.data);
export const createClient = (data: Record<string, unknown>) =>
  api.post("/machines", data).then((r) => r.data);
export const updateClient = (id: string, data: Record<string, unknown>) =>
  api.put(`/machines/${id}`, data).then((r) => r.data);
export const deleteClient = (id: string) => api.delete(`/machines/${id}`);
export const rotateKey = (id: string) =>
  api.post(`/machines/${id}/rotate-key`).then((r) => r.data);
export const restartAgent = (id: string) =>
  api.post(`/machines/${id}/restart-agent`).then((r) => r.data);
export const triggerBackup = (id: string) =>
  api.post(`/machines/${id}/trigger-backup`).then((r) => r.data);
export const fetchClientLogs = (id: string) =>
  api.get(`/machines/${id}/logs`).then((r) => r.data);

// ── Equipamentos ──────────────────────────────────────────────
export const fetchEquipamentos = (clientId: string) =>
  api.get(`/machines/${clientId}/equipamentos`).then((r) => r.data);
export const createEquipamento = (clientId: string, data: Record<string, unknown>) =>
  api.post(`/machines/${clientId}/equipamentos`, data).then((r) => r.data);
export const updateEquipamento = (clientId: string, eqId: string, data: Record<string, unknown>) =>
  api.put(`/machines/${clientId}/equipamentos/${eqId}`, data).then((r) => r.data);
export const deleteEquipamento = (clientId: string, eqId: string) =>
  api.delete(`/machines/${clientId}/equipamentos/${eqId}`);

// ── NVRs (mantido como alias para retrocompatibilidade) ───────
export const fetchNVRs = fetchEquipamentos;
export const createNVR = createEquipamento;
export const updateNVR = updateEquipamento;
export const deleteNVR = deleteEquipamento;

// ── Backups ───────────────────────────────────────────────────
export const fetchBackups = (params?: Record<string, unknown>) =>
  api.get("/backups", { params }).then((r) => r.data);
export const downloadBackupZip = (backupId: string) =>
  api.get(`/backups/${backupId}/download`, { responseType: 'blob' }).then((r) => r.data);

// ── Settings ──────────────────────────────────────────────────
export const fetchSettings = () => api.get("/settings").then((r) => r.data);
export const updateSettings = (data: Record<string, string>) =>
  api.put("/settings", data).then((r) => r.data);

// ── OTA Updates ───────────────────────────────────────────────
export const fetchAgentVersions = () => api.get("/admin/agent-version").then((r) => r.data);
export const createAgentVersion = (data: Record<string, unknown>) =>
  api.post("/admin/agent-version", data).then((r) => r.data);
export const toggleAgentVersion = (id: string) =>
  api.put(`/admin/agent-version/${id}/toggle`).then((r) => r.data);
export const deleteAgentVersion = (id: string) =>
  api.delete(`/admin/agent-version/${id}`).then((r) => r.data);
export const editAgentVersion = (id: string, data: Record<string, string>) =>
  api.put(`/admin/agent-version/${id}`, data).then((r) => r.data);

// ── Clientes (antigos Groups / Unidades) ──────────────────────
export const fetchGroups = (): Promise<ClientGroup[]> =>
  api.get("/clients").then((r) => r.data);

export const fetchGroup = (id: string): Promise<ClientGroup> =>
  api.get(`/clients/${id}`).then((r) => r.data);

export const createGroup = (data: {
  name: string;
  description?: string;
  backup_hour: number;
  backup_minute: number;
  active: boolean;
}): Promise<ClientGroup> => api.post("/clients", data).then((r) => r.data);

export const updateGroup = (
  id: string,
  data: Partial<{
    name: string;
    description: string;
    backup_hour: number;
    backup_minute: number;
    active: boolean;
  }>
): Promise<ClientGroup> => api.put(`/clients/${id}`, data).then((r) => r.data);

export const deleteGroup = (id: string): Promise<void> =>
  api.delete(`/clients/${id}`).then((r) => r.data);

export const triggerGroupBackup = (id: string): Promise<void> =>
  api.post(`/clients/${id}/trigger-backup`).then((r) => r.data);

export const cancelGroupQueue = (id: string): Promise<void> =>
  api.post(`/clients/${id}/cancel-queue`).then((r) => r.data);

export const downloadGroupZip = async (id: string, groupName: string): Promise<void> => {
  const res = await api.get(`/clients/${id}/download-latest`, { responseType: "blob" });
  const blob = new Blob([res.data], { type: "application/zip" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  const date = new Date().toLocaleDateString("pt-BR").replace(/\//g, "-");
  a.download = `cliente_${groupName.replace(/ /g, "_")}_${date}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
};

export default api;
