import type { CSSProperties } from "react";
import { useToast } from "../../../components/Toast";
import { EqForm, EquipamentoConfig, NVR, TipoEquipamento } from "../../../api/types";

export type ToastFn = ReturnType<typeof useToast>["toast"];

// Título dos cards do topo da página da máquina
export const cardTitleStyle: CSSProperties = {
  fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px",
  color: "var(--text-muted)", marginBottom: 16, display: "flex", alignItems: "center", gap: 6,
};

// Intervalo de ping do agente (PING_INTERVAL_S em agent/service.py)
export const AGENT_PING_INTERVAL_MS = 15 * 1000;
// Após o horário previsto, consulta a máquina a cada 1s por este tempo para pegar o novo ping assim que chegar
export const OVERDUE_FAST_POLL_MS = 30 * 1000;

// last_seen é naive em UTC (REGRA-001)
export const serverUtcMs = (iso: string) =>
  new Date(/Z|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z").getTime();

export const TIPOS: TipoEquipamento[] = ["NVR", "OLT", "PABX", "MIKROTIK", "DIGIFORT", "DEFENSE"];
export const TIPO_ICONE_EMOJI: Record<string, string> = {
  NVR: "📹", OLT: "🔌", PABX: "📞", MIKROTIK: "🌐", DIGIFORT: "🖥️", DEFENSE: "🛡️",
};

// Nome seguro para arquivo (espaços -> "_")
export const safeFileName = (s: string) => s.replace(/\s+/g, "_");

export function emptyEqForm(overrides: Partial<EqForm> = {}): EqForm {
  return {
    tipo: "NVR", name: "", ip: "", username: "", password: "",
    pasta_origem: "", fabricante_olt: "UNM2000",
    ...overrides,
  };
}

// Preenche o formulário a partir de um equipamento existente (senha nunca é carregada)
export function eqToForm(eq: NVR): EqForm {
  const cfg = eq.config_extra;
  return {
    tipo: eq.tipo,
    name: eq.name,
    ip: eq.tipo === "DIGIFORT" || (eq.tipo === "OLT" && cfg?.fabricante_olt === "UNM2000") ? "" : eq.ip,
    username: eq.tipo === "OLT" && cfg?.fabricante_olt === "UNM2000" && eq.username === "unm2000" ? "" : eq.username,
    password: "",
    pasta_origem: cfg?.pasta_origem || (eq.tipo === "DIGIFORT" && eq.ip !== "127.0.0.1" ? eq.ip : (eq.tipo === "OLT" && cfg?.fabricante_olt === "UNM2000" && eq.ip !== "127.0.0.1" ? eq.ip : "")),
    fabricante_olt: cfg?.fabricante_olt || "UNM2000",
    caminho_csv: cfg?.caminho_csv || "",
    caminho_log_csv: cfg?.caminho_log_csv || "",
    marca: cfg?.marca || "Hikvision",
  };
}

export interface EqPayload {
  tipo: TipoEquipamento;
  name: string;
  ip: string;
  username: string;
  password?: string;
  config_extra: EquipamentoConfig | null;
}

export function buildEqPayload(
  eqForm: EqForm,
  editingEqId: string | null
): { error?: string; payload?: EqPayload } {
  if (!eqForm.name.trim()) return { error: "Preencha o nome do equipamento." };
  const payload: EqPayload = { tipo: eqForm.tipo, name: eqForm.name.trim(), ip: "", username: "", password: "", config_extra: null };

  if (eqForm.tipo === "NVR" || eqForm.tipo === "PABX" || eqForm.tipo === "MIKROTIK" || eqForm.tipo === "CAMERA") {
    if (!eqForm.ip || (!editingEqId && (!eqForm.username || !eqForm.password))) return { error: `Para ${eqForm.tipo}, preencha IP/Host, usuário e senha.` };
    payload.ip = eqForm.ip.trim(); payload.username = eqForm.username.trim(); payload.password = eqForm.password;
    if (eqForm.tipo === "CAMERA") {
      payload.config_extra = { modelo: eqForm.modelo || "Hikvision" };
    } else if (eqForm.tipo === "NVR") {
      payload.config_extra = { marca: eqForm.marca || "Hikvision" };
    }
  } else if (eqForm.tipo === "DIGIFORT") {
    if (!eqForm.pasta_origem) return { error: "Para DIGIFORT, informe a pasta de origem." };
    payload.ip = "127.0.0.1";
    payload.username = "digifort";
    payload.password = "digifort";
    payload.config_extra = {
      pasta_origem: eqForm.pasta_origem.trim(),
      caminho_csv: eqForm.caminho_csv?.trim() || "",
      caminho_log_csv: eqForm.caminho_log_csv?.trim() || "",
    };
  } else if (eqForm.tipo === "OLT") {
    if (!eqForm.fabricante_olt) return { error: "Selecione o sistema da OLT." };
    const cfg: EquipamentoConfig = { fabricante_olt: eqForm.fabricante_olt };
    payload.config_extra = cfg;
    if (eqForm.fabricante_olt === "UNM2000") {
      if (!eqForm.pasta_origem) return { error: "Para UNM2000, informe a pasta de origem dos backups." };
      payload.ip = "127.0.0.1";
      cfg.pasta_origem = eqForm.pasta_origem.trim();
      const usuarioApi = eqForm.username.trim();
      if (!usuarioApi) {
        payload.username = "unm2000";
        payload.password = "unm2000";
      } else {
        if (!editingEqId && !eqForm.password) {
          return { error: "Para a exportação na hora, informe usuário e senha da API do UNM2000." };
        }
        payload.username = usuarioApi;
        payload.password = eqForm.password;
        cfg.exportar_no_manual = true;
      }
    } else if (eqForm.fabricante_olt === "HUAWEI" || eqForm.fabricante_olt === "VSOL") {
      if (!eqForm.ip || (!editingEqId && (!eqForm.username || !eqForm.password))) return { error: `Para ${eqForm.fabricante_olt}, preencha IP, usuário e senha.` };
      payload.ip = eqForm.ip.trim(); payload.username = eqForm.username.trim(); payload.password = eqForm.password;
      if (eqForm.fabricante_olt === "HUAWEI") cfg.pasta_origem = eqForm.pasta_origem.trim();
    }
  } else if (eqForm.tipo === "DEFENSE") {
    if (!eqForm.pasta_origem) return { error: "Para DEFENSE, informe a pasta de origem." };
    payload.ip = "127.0.0.1";
    payload.username = "defense";
    payload.password = "defense";
    payload.config_extra = {
      pasta_origem: eqForm.pasta_origem.trim(),
    };
  }
  // Remove blank passwords in edit mode so backend ignores them
  if (editingEqId && !payload.password) delete payload.password;
  return { payload };
}

// "a@x.com, b@x.com" -> ["a@x.com", "b@x.com"]
export const parseEmails = (s: string) => s.split(",").map(e => e.trim()).filter(Boolean);
