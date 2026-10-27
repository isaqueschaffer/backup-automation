import api from "./client";
import {
  Conta,
  ContaDetalhe,
  Me,
  Plano,
  TipoConta,
  Usuario,
} from "./types";

export interface NovaContaPayload {
  nome: string;
  tipo: TipoConta;
  documento?: string | null;
  email_contato?: string | null;
  telefone?: string | null;
  observacoes?: string | null;
  plano_id: string;
  admin: {
    nome: string;
    email: string;
    senha: string;
  };
}

export interface EditarContaPayload {
  nome: string;
  tipo: TipoConta;
  documento: string | null;
  email_contato: string | null;
  telefone: string | null;
  observacoes: string | null;
  expira_em: string;
}

// ── Auth & Usuário corrente ──────────────────────────────────────────

export const fetchMe = (): Promise<Me> =>
  api.get("/auth/me").then((r) => r.data);

export const trocarSenha = (
  senha_atual: string,
  senha_nova: string
): Promise<{ access_token: string }> =>
  api.post("/auth/trocar-senha", { senha_atual, senha_nova }).then((r) => r.data);

// ── Super admin: Planos ──────────────────────────────────────────────

export const fetchPlanos = (): Promise<Plano[]> =>
  api.get("/admin/planos").then((r) => r.data);

export const createPlano = (data: {
  nome: string;
  duracao_dias: number;
}): Promise<Plano> => api.post("/admin/planos", data).then((r) => r.data);

export const updatePlano = (
  id: string,
  data: Partial<Pick<Plano, "nome" | "duracao_dias" | "ativo">>
): Promise<Plano> => api.put(`/admin/planos/${id}`, data).then((r) => r.data);

// ── Super admin: Contas ──────────────────────────────────────────────

export const fetchContas = (): Promise<Conta[]> =>
  api.get("/admin/contas").then((r) => r.data);

export const fetchConta = (id: string): Promise<ContaDetalhe> =>
  api.get(`/admin/contas/${id}`).then((r) => r.data);

export const createConta = (data: NovaContaPayload): Promise<ContaDetalhe> =>
  api.post("/admin/contas", data).then((r) => r.data);

export const updateConta = (
  id: string,
  data: Partial<EditarContaPayload>
): Promise<ContaDetalhe> => api.put(`/admin/contas/${id}`, data).then((r) => r.data);

export const renovarConta = (id: string, plano_id: string): Promise<ContaDetalhe> =>
  api.post(`/admin/contas/${id}/renovar`, { plano_id }).then((r) => r.data);

export const suspenderConta = (id: string): Promise<ContaDetalhe> =>
  api.post(`/admin/contas/${id}/suspender`).then((r) => r.data);

export const reativarConta = (id: string): Promise<ContaDetalhe> =>
  api.post(`/admin/contas/${id}/reativar`).then((r) => r.data);

export const moverClienteDeConta = (
  customerId: string,
  conta_id: string
): Promise<{ status: string; maquinas_movidas: number }> =>
  api.post(`/admin/clientes/${customerId}/mover-conta`, { conta_id }).then((r) => r.data);

// ── Super admin: Super administradores ───────────────────────────────

export const fetchSuperAdmins = (): Promise<Usuario[]> =>
  api.get("/admin/super-admins").then((r) => r.data);

export const createSuperAdmin = (data: {
  nome: string;
  email: string;
  senha: string;
}): Promise<Usuario> => api.post("/admin/super-admins", data).then((r) => r.data);

export const updateSuperAdmin = (
  id: string,
  data: { nome?: string; ativo?: boolean; senha?: string }
): Promise<Usuario> => api.put(`/admin/super-admins/${id}`, data).then((r) => r.data);

// ── Gestão da Conta & Usuários da Conta ──────────────────────────────

export const fetchMinhaConta = (): Promise<ContaDetalhe> =>
  api.get("/conta").then((r) => r.data);

export const fetchUsuariosConta = (contaId?: string): Promise<Usuario[]> => {
  const config = contaId ? { headers: { "X-Conta-ID": contaId } } : undefined;
  return api.get("/conta/usuarios", config).then((r) => r.data);
};

export const createUsuarioConta = (
  data: {
    nome: string;
    email: string;
    senha: string;
    papel: "ADMIN" | "LEITURA";
  },
  contaId?: string
): Promise<Usuario> => {
  const config = contaId ? { headers: { "X-Conta-ID": contaId } } : undefined;
  return api.post("/conta/usuarios", data, config).then((r) => r.data);
};

export const updateUsuarioConta = (
  id: string,
  data: {
    nome?: string;
    papel?: "ADMIN" | "LEITURA";
    ativo?: boolean;
    senha?: string;
  },
  contaId?: string
): Promise<Usuario> => {
  const config = contaId ? { headers: { "X-Conta-ID": contaId } } : undefined;
  return api.put(`/conta/usuarios/${id}`, data, config).then((r) => r.data);
};
