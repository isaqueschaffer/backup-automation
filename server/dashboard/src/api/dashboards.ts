/// <reference types="vite/client" />
import axios from "axios";
import api from "./client";
import {
  Compartilhamento,
  DadosDashboard,
  DashboardAdmin,
  DashboardLayout,
  DashboardPublico,
  LinkGerado,
  OpcoesDashboard,
  TipoWidgetCatalogo,
} from "../pages/Dashboards/types";

// ── Cliente administrativo (usa JWT já configurado) ───────────────────

export const fetchWidgetCatalog = (): Promise<TipoWidgetCatalogo[]> =>
  api.get("/dashboards/widgets").then((r) => r.data);

export const fetchDashboard = (customerId: string): Promise<DashboardAdmin> =>
  api.get(`/clients/${customerId}/dashboard`).then((r) => r.data);

export const saveDashboardLayout = (
  customerId: string,
  layout: DashboardLayout,
  version: number
): Promise<{ layout: DashboardLayout; version: number }> =>
  api.put(`/clients/${customerId}/dashboard`, { layout, version }).then((r) => r.data);

export const restoreDashboardDefault = (
  customerId: string
): Promise<{ layout: DashboardLayout; version: number }> =>
  api.post(`/clients/${customerId}/dashboard/restore-default`).then((r) => r.data);

export const fetchDashboardData = (customerId: string): Promise<DadosDashboard> =>
  api.get(`/clients/${customerId}/dashboard/data`).then((r) => r.data);

export const fetchDashboardPreview = (
  customerId: string,
  layout: DashboardLayout
): Promise<DadosDashboard> =>
  api.post(`/clients/${customerId}/dashboard/preview`, { layout }).then((r) => r.data);

export const fetchDashboardOptions = (customerId: string): Promise<OpcoesDashboard> =>
  api.get(`/clients/${customerId}/dashboard/opcoes`).then((r) => r.data);

export const createShareLink = (
  customerId: string,
  body: { expira_em?: string | null; permite_edicao: boolean }
): Promise<LinkGerado> =>
  api.post(`/clients/${customerId}/dashboard/share`, body).then((r) => r.data);

export const updateShareLink = (
  customerId: string,
  body: {
    ativo?: boolean;
    expira_em?: string;
    limpar_expiracao?: boolean;
    permite_edicao?: boolean;
  }
): Promise<Compartilhamento> =>
  api.put(`/clients/${customerId}/dashboard/share`, body).then((r) => r.data);

export const revokeShareLink = (customerId: string): Promise<void> =>
  api.delete(`/clients/${customerId}/dashboard/share`).then((r) => r.data);

// ── Cliente público (somente token por cabeçalho, sem JWT) ────────────

const API_BASE = import.meta.env.VITE_API_URL || "";

const publico = axios.create({
  baseURL: `${API_BASE}/api/v1/public/dashboard`,
  headers: { "Content-Type": "application/json" },
});

export const fetchPublicDashboard = (token: string): Promise<DashboardPublico> =>
  publico.get("", { headers: { "X-Dashboard-Token": token } }).then((r) => r.data);

export const fetchPublicData = (token: string): Promise<DadosDashboard> =>
  publico.get("/data", { headers: { "X-Dashboard-Token": token } }).then((r) => r.data);

export const fetchPublicPreview = (
  token: string,
  layout: DashboardLayout
): Promise<DadosDashboard> =>
  publico
    .post("/preview", { layout }, { headers: { "X-Dashboard-Token": token } })
    .then((r) => r.data);

export const fetchPublicOptions = (token: string): Promise<OpcoesDashboard> =>
  publico.get("/opcoes", { headers: { "X-Dashboard-Token": token } }).then((r) => r.data);

export const savePublicLayout = (
  token: string,
  layout: DashboardLayout,
  version: number
): Promise<{ layout: DashboardLayout; version: number }> =>
  publico.put("/layout", { layout, version }, { headers: { "X-Dashboard-Token": token } }).then((r) => r.data);
