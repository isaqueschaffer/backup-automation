/// <reference types="vite/client" />
import axios from "axios";

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

// ── Clients ───────────────────────────────────────────────────
export const fetchClients = () => api.get("/clients").then((r) => r.data);
export const fetchClient = (id: string) => api.get(`/clients/${id}`).then((r) => r.data);
export const createClient = (data: Record<string, unknown>) =>
  api.post("/clients", data).then((r) => r.data);
export const updateClient = (id: string, data: Record<string, unknown>) =>
  api.put(`/clients/${id}`, data).then((r) => r.data);
export const deleteClient = (id: string) => api.delete(`/clients/${id}`);
export const rotateKey = (id: string) =>
  api.post(`/clients/${id}/rotate-key`).then((r) => r.data);
export const restartAgent = (id: string) =>
  api.post(`/clients/${id}/restart-agent`).then((r) => r.data);
export const triggerBackup = (id: string) =>
  api.post(`/clients/${id}/trigger-backup`).then((r) => r.data);

// ── Equipamentos (novo endpoint genérico) ────────────────────
export const fetchEquipamentos = (clientId: string) =>
  api.get(`/clients/${clientId}/equipamentos`).then((r) => r.data);
export const createEquipamento = (clientId: string, data: Record<string, unknown>) =>
  api.post(`/clients/${clientId}/equipamentos`, data).then((r) => r.data);
export const updateEquipamento = (clientId: string, eqId: string, data: Record<string, unknown>) =>
  api.put(`/clients/${clientId}/equipamentos/${eqId}`, data).then((r) => r.data);
export const deleteEquipamento = (clientId: string, eqId: string) =>
  api.delete(`/clients/${clientId}/equipamentos/${eqId}`);

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

export default api;
