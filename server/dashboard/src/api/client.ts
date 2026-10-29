/// <reference types="vite/client" />
import axios from "axios";
import { AgentLog, Customer, CustomerRun, Machine, PaginatedBackups } from "./types";
import { saveBlob } from "../utils/download";

const API_BASE = import.meta.env.VITE_API_URL || "";

// Conta escolhida pelo administrador da plataforma (enviada em X-Conta-ID)
export const CONTA_KEY = "trilan_conta_id";

const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("trilan_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  try {
    const contaId = localStorage.getItem(CONTA_KEY);
    if (contaId && !config.headers["X-Conta-ID"]) {
      config.headers["X-Conta-ID"] = contaId;
    }
  } catch {
    // localStorage indisponível
  }
  return config;
});

// Redirect to login on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const isLogin = String(err.config?.url || "").includes("/auth/login");
    if (err.response?.status === 401 && !isLogin) {
      localStorage.removeItem("trilan_token");
      if (window.location.pathname !== "/login") window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────
// Com e-mail: usuário de uma conta. Sem e-mail: administrador da plataforma (senha única).
export const login = (email: string | null, password: string) =>
  api.post("/auth/login", email ? { email, password } : { password }).then((r) => r.data);

// ── Stats ─────────────────────────────────────────────────────
export const fetchStats = () => api.get("/stats").then((r) => r.data);

// ── Máquinas (computadores com o agente) ──────────────────────
export const fetchMachines = (params?: { customer_id?: string; unassigned?: boolean }): Promise<Machine[]> =>
  api.get("/machines", { params }).then((r) => r.data);
export const fetchMachine = (id: string): Promise<Machine> =>
  api.get(`/machines/${id}`).then((r) => r.data);
export const createMachine = (data: Record<string, unknown>): Promise<Machine> =>
  api.post("/machines", data).then((r) => r.data);
export const updateMachine = (id: string, data: Record<string, unknown>): Promise<Machine> =>
  api.put(`/machines/${id}`, data).then((r) => r.data);
export const deleteMachine = (id: string) => api.delete(`/machines/${id}`);
export const rotateMachineKey = (id: string): Promise<Machine> =>
  api.post(`/machines/${id}/rotate-key`).then((r) => r.data);
export const restartMachineAgent = (id: string) =>
  api.post(`/machines/${id}/restart-agent`).then((r) => r.data);
export const triggerMachineBackup = (id: string) =>
  api.post(`/machines/${id}/trigger-backup`).then((r) => r.data);
export const triggerBackupAll = () =>
  api.post("/machines/trigger-backup-all").then((r) => r.data);
export const restartAgentAll = () =>
  api.post("/machines/restart-agent-all").then((r) => r.data);
export interface FiltrosLogs {
  incluirPings?: boolean;
  nivel?: string;
  q?: string;
  equipamento?: string;
  limit?: number;
}

export const fetchMachineLogs = (
  id: string,
  { incluirPings = true, nivel, q, equipamento, limit }: FiltrosLogs = {}
): Promise<AgentLog[]> => {
  const params: Record<string, unknown> = { incluir_pings: incluirPings };
  if (nivel) params.nivel = nivel;
  if (q && q.trim()) params.q = q.trim();
  if (equipamento && equipamento.trim()) params.equipamento = equipamento.trim();
  if (limit !== undefined && limit !== null) params.limit = limit;
  return api.get(`/machines/${id}/logs`, { params }).then((r) => r.data);
};

// ── Equipamentos ──────────────────────────────────────────────
export const fetchEquipamentos = (machineId: string) =>
  api.get(`/machines/${machineId}/equipamentos`).then((r) => r.data);
export const createEquipamento = (machineId: string, data: Record<string, unknown>) =>
  api.post(`/machines/${machineId}/equipamentos`, data).then((r) => r.data);
export const updateEquipamento = (machineId: string, eqId: string, data: Record<string, unknown>) =>
  api.put(`/machines/${machineId}/equipamentos/${eqId}`, data).then((r) => r.data);
export const deleteEquipamento = (machineId: string, eqId: string) =>
  api.delete(`/machines/${machineId}/equipamentos/${eqId}`);

// ── Backups ───────────────────────────────────────────────────
export interface BackupQuery {
  page?: number;
  size?: number;
  status?: string;
  date_from?: string;
  date_to?: string;
  machine_id?: string;
  customer_id?: string;
}
export const fetchBackups = (params?: BackupQuery): Promise<PaginatedBackups> =>
  api.get("/backups", { params }).then((r) => r.data);
export const downloadBackupZip = (backupId: string, options?: { direct_machine?: boolean }) => {
  const params = options?.direct_machine ? { direct_machine: true } : {};
  return api.get(`/backups/${backupId}/download`, { responseType: 'blob', params }).then((r) => r.data);
};
export const resendBackupEmail = (backupId: string) =>
  api.post(`/backups/${backupId}/resend-email`).then((r) => r.data);

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

// ── Clientes (empresas atendidas; cada um agrupa Máquinas) ────
export const fetchCustomers = (): Promise<Customer[]> =>
  api.get("/clients").then((r) => r.data);

export const fetchCustomer = (id: string): Promise<Customer> =>
  api.get(`/clients/${id}`).then((r) => r.data);

export const createCustomer = (data: {
  name: string;
  description?: string;
  backup_hour: number;
  backup_minute: number;
  email_to: string[];
  active: boolean;
  zip_password?: string;
}): Promise<Customer> => api.post("/clients", data).then((r) => r.data);

export const updateCustomer = (
  id: string,
  data: Partial<{
    name: string;
    description: string | null;
    backup_hour: number;
    backup_minute: number;
    email_to: string[];
    active: boolean;
    zip_password: string | null;
  }>
): Promise<Customer> => api.put(`/clients/${id}`, data).then((r) => r.data);

// ── Rodadas de backup do cliente (1 e-mail por rodada) ────────
export const fetchCustomerRuns = (customerId: string, limit = 20): Promise<CustomerRun[]> =>
  api.get(`/clients/${customerId}/runs`, { params: { limit } }).then((r) => r.data);

// ZIP unificado da rodada (uma pasta por máquina). Erros vêm dentro do blob: use extractBlobError.
export const downloadCustomerRunZip = async (customerId: string, runId: string, nomeArquivo: string): Promise<void> => {
  const res = await api.get(`/clients/${customerId}/runs/${runId}/download`, { responseType: "blob" });
  saveBlob(res.data, nomeArquivo);
};

// Reenvia o e-mail de uma rodada fechada (409 se ainda estiver em andamento)
export const resendCustomerRunEmail = (customerId: string, runId: string): Promise<{ email_sent: boolean }> =>
  api.post(`/clients/${customerId}/runs/${runId}/resend-email`).then((r) => r.data);

export const deleteCustomer = (id: string): Promise<void> =>
  api.delete(`/clients/${id}`).then((r) => r.data);

export const triggerCustomerBackup = (id: string): Promise<void> =>
  api.post(`/clients/${id}/trigger-backup`).then((r) => r.data);

export const cancelCustomerQueue = (id: string): Promise<void> =>
  api.post(`/clients/${id}/cancel-queue`).then((r) => r.data);

// Vincula a máquina ao cliente (entra no fim da fila e herda o horário)
export const attachMachine = (customerId: string, machineId: string): Promise<Customer> =>
  api.post(`/clients/${customerId}/machines/${machineId}`).then((r) => r.data);

// Desvincula a máquina do cliente (ela mantém o horário atual)
export const detachMachine = (customerId: string, machineId: string): Promise<Customer> =>
  api.delete(`/clients/${customerId}/machines/${machineId}`).then((r) => r.data);

// Grava a ordem da fila: machineIds precisa conter exatamente as máquinas do cliente
export const reorderCustomerQueue = (customerId: string, machineIds: string[]): Promise<Customer> =>
  api.put(`/clients/${customerId}/queue-order`, { machine_ids: machineIds }).then((r) => r.data);

export const downloadCustomerZip = async (id: string, customerName: string): Promise<void> => {
  const res = await api.get(`/clients/${id}/download-latest`, { responseType: "blob" });
  const blob = new Blob([res.data], { type: "application/zip" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  const date = new Date().toLocaleDateString("pt-BR").replace(/\//g, "-");
  a.download = `cliente_${customerName.replace(/ /g, "_")}_${date}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
};

export default api;
