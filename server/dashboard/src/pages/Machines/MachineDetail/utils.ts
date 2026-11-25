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

export const TIPOS: TipoEquipamento[] = ["NVR", "OLT", "PABX", "MIKROTIK", "ANTENA", "DIGIFORT", "DEFENSE"];
export const TIPO_ICONE_EMOJI: Record<string, string> = {
  NVR: "📹", OLT: "🔌", PABX: "📞", MIKROTIK: "🌐", ANTENA: "📡", DIGIFORT: "🖥️", DEFENSE: "🛡️",
};

// Nome seguro para arquivo (espaços -> "_")
export const safeFileName = (s: string) => s.replace(/\s+/g, "_");

// Conta que o script public/preparar_acesso_ssh.ps1 cria na máquina do cliente (no grupo Administradores, em
// Windows de qualquer idioma). É o padrão do campo "Usuário SSH" do acesso remoto (agente no MikroTik); dá para trocar.
export const USUARIO_SSH_PADRAO = "trilan_backup";

export function emptyEqForm(overrides: Partial<EqForm> = {}): EqForm {
  return {
    tipo: "NVR", name: "", ip: "", username: "", password: "",
    pasta_origem: "", fabricante_olt: "UNM2000",
    porta_api: 4433,
    porta_alarme: 3001,
    porta_ssh: 22,
    prefixos_mac: "",
    smb_host: "",
    smb_usuario: "",
    smb_senha: "",
    smb_senha_definida: false,
    ssh_usuario: "",
    ssh_senha: "",
    ssh_senha_definida: false,
    ssh_porta: "",
    acesso_remoto: "sftp",
    ssh_chave: "",
    ssh_chave_definida: false,
    ssh_fingerprint: "",
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
    username: eq.tipo === "DEFENSE" ? (eq.username || "system") : (eq.tipo === "OLT" && cfg?.fabricante_olt === "UNM2000" && eq.username === "unm2000" ? "" : eq.username),
    password: "",
    pasta_origem: cfg?.pasta_origem || (eq.tipo === "DIGIFORT" && eq.ip !== "127.0.0.1" ? eq.ip : (eq.tipo === "OLT" && cfg?.fabricante_olt === "UNM2000" && eq.ip !== "127.0.0.1" ? eq.ip : "")),
    fabricante_olt: cfg?.fabricante_olt || "UNM2000",
    caminho_csv: cfg?.caminho_csv || "",
    caminho_log_csv: cfg?.caminho_log_csv || "",
    pasta_gravacoes: cfg?.pasta_gravacoes || "",
    marca: cfg?.marca || "Hikvision",
    porta_api: cfg?.porta_api ?? 4433,
    porta_alarme: cfg?.porta_alarme ?? 3001,
    olts: cfg?.olts || "",
    telnet_usuario: cfg?.telnet_usuario || "",
    telnet_senha: "",
    telnet_enable: "",
    telnet_senha_definida: !!cfg?.telnet_senha_definida,
    nomes_db_host: cfg?.nomes_db_host || "",
    nomes_db_usuario: cfg?.nomes_db_usuario || "",
    nomes_db_senha: "",
    nomes_db_senha_definida: !!cfg?.nomes_db_senha_definida,
    licenca_inicio: cfg?.licenca_inicio || "",
    licenca_fim: cfg?.licenca_fim || "",
    porta_ssh: cfg?.porta_ssh ?? 22,
    prefixos_mac: cfg?.prefixos_mac || "",
    antenas: cfg?.antenas || [],
    smb_host: cfg?.smb_host || "",
    smb_usuario: cfg?.smb_usuario || "",
    smb_senha: "",
    smb_senha_definida: !!cfg?.smb_senha_definida,
    ssh_usuario: cfg?.ssh_usuario || "",
    ssh_senha: "",
    ssh_senha_definida: !!cfg?.ssh_senha_definida,
    ssh_porta: cfg?.ssh_porta ?? "",
    // Cadastro antigo sem o campo: o agente segue no SMB provisionado, então o formulário mostra o que já vale
    acesso_remoto: cfg?.acesso_remoto || (cfg?.ssh_usuario || cfg?.smb_host ? "smb" : "sftp"),
    ssh_chave: "",
    ssh_chave_definida: !!cfg?.ssh_chave_definida,
    ssh_fingerprint: cfg?.ssh_fingerprint || "",
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

// Acesso remoto à máquina do cliente (UNM2000 / Digifort / Defense com agente no MikroTik). Devolve a mensagem de erro, se houver.
function aplicarAcessoRemoto(cfg: EquipamentoConfig, eqForm: EqForm, agenteTipo?: "WINDOWS" | "MIKROTIK", editando?: boolean, ipPadrao?: string): string | null {
  if (eqForm.smb_host?.trim()) cfg.smb_host = eqForm.smb_host.trim();
  if (eqForm.smb_usuario?.trim()) cfg.smb_usuario = eqForm.smb_usuario.trim();
  if (eqForm.smb_senha) cfg.smb_senha = eqForm.smb_senha;
  if (eqForm.ssh_usuario?.trim()) cfg.ssh_usuario = eqForm.ssh_usuario.trim();
  // Senha e chave só vão se digitadas; em branco o servidor mantém as atuais
  if (eqForm.ssh_senha) cfg.ssh_senha = eqForm.ssh_senha;
  if (eqForm.ssh_chave?.trim()) cfg.ssh_chave = eqForm.ssh_chave.trim();
  if (eqForm.ssh_porta) cfg.ssh_porta = Number(eqForm.ssh_porta);
  if (eqForm.ssh_fingerprint?.trim()) cfg.ssh_fingerprint = eqForm.ssh_fingerprint.trim();
  if (agenteTipo === "MIKROTIK") {
    cfg.acesso_remoto = eqForm.acesso_remoto === "smb" ? "smb" : "sftp";
    if (!cfg.smb_host && !ipPadrao) return "Agente no MikroTik: informe o IP da máquina deste equipamento para acessar a pasta.";
    if (cfg.acesso_remoto === "sftp") {
      if (!cfg.ssh_usuario) return "Acesso por SFTP: informe o usuário SSH da máquina.";
      const temSenha = !!eqForm.ssh_senha || (!!editando && !!eqForm.ssh_senha_definida);
      const temChave = !!eqForm.ssh_chave?.trim() || (!!editando && !!eqForm.ssh_chave_definida);
      if (!temSenha && !temChave) return "Acesso por SFTP: informe a senha ou a chave privada do usuário SSH.";
      if (cfg.ssh_chave && !/PRIVATE KEY/.test(cfg.ssh_chave.slice(0, 80))) return "A chave SSH precisa ser a chave PRIVADA (-----BEGIN ... PRIVATE KEY-----).";
      if (cfg.ssh_fingerprint && !/^(SHA256:)?[A-Za-z0-9+/]{43}=?$/.test(cfg.ssh_fingerprint)) return "Impressão digital inválida: use o formato SHA256:... (ssh-keygen -lf).";
    }
  } else if (cfg.ssh_usuario && !cfg.smb_host) {
    return "Informe o IP da máquina deste equipamento para acessar a pasta.";
  }
  return null;
}

export function buildEqPayload(
  eqForm: EqForm,
  editingEqId: string | null,
  agenteTipo?: "WINDOWS" | "MIKROTIK"
): { error?: string; payload?: EqPayload } {
  if (!eqForm.name.trim()) return { error: "Preencha o nome do equipamento." };
  const payload: EqPayload = { tipo: eqForm.tipo, name: eqForm.name.trim(), ip: "", username: "", password: "", config_extra: null };

  if (eqForm.tipo === "NVR" || eqForm.tipo === "PABX" || eqForm.tipo === "MIKROTIK" || eqForm.tipo === "CAMERA" || eqForm.tipo === "ANTENA") {
    if (!eqForm.ip || (!editingEqId && (!eqForm.username || !eqForm.password))) return { error: `Para ${eqForm.tipo}, preencha IP/Host, usuário e senha.` };
    payload.ip = eqForm.ip.trim(); payload.username = eqForm.username.trim(); payload.password = eqForm.password;
    if (eqForm.tipo === "CAMERA") {
      payload.config_extra = { modelo: eqForm.modelo || "Hikvision" };
    } else if (eqForm.tipo === "NVR") {
      payload.config_extra = { marca: eqForm.marca || "Hikvision" };
    } else if (eqForm.tipo === "ANTENA") {
      const porta = Number(eqForm.porta_ssh) || 22;
      if (porta < 1 || porta > 65535) return { error: "A porta SSH do MikroTik deve estar entre 1 e 65535." };
      // A lista de antenas vem do que já está cadastrado (ela é editada no botão "Antenas" do card)
      payload.config_extra = { porta_ssh: porta, prefixos_mac: (eqForm.prefixos_mac || "").trim(), antenas: eqForm.antenas || [] };
    }
  } else if (eqForm.tipo === "DIGIFORT") {
    if (!eqForm.pasta_origem) return { error: "Para DIGIFORT, informe a pasta de backup." };
    if (!eqForm.planilhaNova && !eqForm.planilhaSalva) return { error: "Para DIGIFORT, carregue a planilha das câmeras." };
    payload.ip = "127.0.0.1";
    payload.username = "digifort";
    payload.password = "digifort";
    const cfg: EquipamentoConfig = {
      pasta_origem: eqForm.pasta_origem.trim(),
      caminho_csv: eqForm.caminho_csv?.trim() || "",
      caminho_log_csv: eqForm.caminho_log_csv?.trim() || "",
      pasta_gravacoes: eqForm.pasta_gravacoes?.trim() || "",
    };
    const erroAcesso = aplicarAcessoRemoto(cfg, eqForm, agenteTipo, !!editingEqId);
    if (erroAcesso) return { error: erroAcesso };
    payload.config_extra = cfg;
  } else if (eqForm.tipo === "OLT") {
    if (!eqForm.fabricante_olt) return { error: "Selecione o sistema da OLT." };
    const cfg: EquipamentoConfig = { fabricante_olt: eqForm.fabricante_olt };
    payload.config_extra = cfg;
    if (eqForm.fabricante_olt === "UNM2000") {
      if (!eqForm.pasta_origem) return { error: "Para UNM2000, informe a pasta de origem dos backups." };
      payload.ip = "127.0.0.1";
      cfg.pasta_origem = eqForm.pasta_origem.trim();
      cfg.olts = (eqForm.olts || "").trim();
      if (/[\s,;=]/.test(cfg.olts)) return { error: "Informe um só IP de OLT por equipamento (crie outro equipamento para cada OLT)." };
      cfg.telnet_usuario = (eqForm.telnet_usuario || "").trim();
      // Senhas só vão se digitadas; em branco o servidor mantém a atual
      if (eqForm.telnet_senha) cfg.telnet_senha = eqForm.telnet_senha;
      if (eqForm.telnet_enable) cfg.telnet_enable = eqForm.telnet_enable;
      cfg.nomes_db_host = (eqForm.nomes_db_host || "").trim();
      cfg.nomes_db_usuario = (eqForm.nomes_db_usuario || "").trim();
      if (eqForm.nomes_db_senha) cfg.nomes_db_senha = eqForm.nomes_db_senha;
      cfg.licenca_inicio = eqForm.licenca_inicio || "";
      cfg.licenca_fim = eqForm.licenca_fim || "";
      const erroAcesso = aplicarAcessoRemoto(cfg, eqForm, agenteTipo, !!editingEqId);
      if (erroAcesso) return { error: erroAcesso };
      if (cfg.olts) {
        if (!cfg.telnet_usuario) return { error: "Para monitorar as OLTs, informe o usuário do Telnet." };
        if (!eqForm.telnet_senha && !(editingEqId && eqForm.telnet_senha_definida)) return { error: "Para monitorar as OLTs, informe a senha do Telnet." };
      }
      payload.username = "unm2000";
      payload.password = "unm2000";
    } else if (eqForm.fabricante_olt === "HUAWEI" || eqForm.fabricante_olt === "VSOL") {
      if (!eqForm.ip || (!editingEqId && (!eqForm.username || !eqForm.password))) return { error: `Para ${eqForm.fabricante_olt}, preencha IP, usuário e senha.` };
      payload.ip = eqForm.ip.trim(); payload.username = eqForm.username.trim(); payload.password = eqForm.password;
      if (eqForm.fabricante_olt === "HUAWEI") cfg.pasta_origem = eqForm.pasta_origem.trim();
    }
  } else if (eqForm.tipo === "DEFENSE") {
    if (!eqForm.ip.trim()) return { error: "Para DEFENSE, informe o endereço IP ou host do servidor." };
    if (!editingEqId && !eqForm.password) return { error: "Para DEFENSE, informe a senha da API." };
    payload.ip = eqForm.ip.trim();
    payload.username = eqForm.username.trim() || "system";
    payload.password = eqForm.password;
    if (agenteTipo === "MIKROTIK" && !eqForm.pasta_origem.trim()) return { error: "Agente no MikroTik: configure a pasta de backup do Defense (o agente lê o arquivo gerado por ele)." };
    const cfgDefense: EquipamentoConfig = {
      pasta_origem: eqForm.pasta_origem.trim(),
      porta_api: Number(eqForm.porta_api) || 4433,
      porta_alarme: Number(eqForm.porta_alarme) || 3001,
    };
    const erroAcessoDefense = aplicarAcessoRemoto(cfgDefense, eqForm, agenteTipo, !!editingEqId, payload.ip);
    if (erroAcessoDefense) return { error: erroAcessoDefense };
    payload.config_extra = cfgDefense;
  }
  // Remove blank passwords in edit mode so backend ignores them
  if (editingEqId && !payload.password) delete payload.password;
  return { payload };
}

// "a@x.com, b@x.com" -> ["a@x.com", "b@x.com"]
export const parseEmails = (s: string) => s.split(",").map(e => e.trim()).filter(Boolean);