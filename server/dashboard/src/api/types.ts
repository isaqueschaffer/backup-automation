export type TipoEquipamento = "NVR" | "OLT" | "ONU" | "PABX" | "MIKROTIK" | "DIGIFORT" | "DEFENSE" | "CAMERA" | "MIXED";

// Status de gravação de uma câmera (NVR.last_recording_status)
export interface CameraRecStatus {
  nome?: string;
  canal?: number;
  online?: boolean;
  status_comunicacao?: string;
  status_gravacao?: string;
  mapa?: string;
  total_dias?: number;
  dias_gravados?: number | null;
  // Digifort: pasta de gravação usada pelo agente para a câmera (null = nenhuma pasta com o nome da câmera)
  pasta_gravacao?: string | null;
}

// Disco reportado pela telemetria do NVR (NVR.last_telemetry_status)
export interface NVRTelemetryDisk {
  device?: string;
  status?: string;
  percent?: number | null;
  total_gb?: number | null;
  free_gb?: number | null;
  power_on_days?: number | null;
  temperature_c?: number | null;
}

export interface NVRTelemetryNet {
  name: string;
  ip?: string | null;
  mac?: string | null;
  status?: string | null;
  speed_mbps?: number | null;
  recv_mbps?: number | null;
  sent_mbps?: number | null;
}

// Telemetria de CPU/RAM/discos/rede do NVR
export interface NVRTelemetry {
  cpu_percent?: number | null;
  ram_percent?: number | null;
  ram_total_gb?: number | null;
  ram_used_gb?: number | null;
  uptime_seconds?: number | null;
  disks?: NVRTelemetryDisk[];
  networks?: NVRTelemetryNet[];
}

export interface EquipamentoConfig {
  pasta_origem?: string;
  fabricante_olt?: string;
  exportar_no_manual?: boolean;
  caminho_csv?: string;
  caminho_log_csv?: string;
  pasta_gravacoes?: string;
  marca?: string;
  modelo?: string;
  porta_api?: number;
  [key: string]: unknown;
}

// Estado do formulário de equipamento (MachineDetail)
export interface EqForm {
  tipo: TipoEquipamento;
  name: string;
  ip: string;
  username: string;
  password: string;
  pasta_origem: string;
  fabricante_olt: string;
  modelo?: string;
  marca?: string;
  caminho_csv?: string;
  caminho_log_csv?: string;
  pasta_gravacoes?: string;
  porta_api?: number | string;
  // Planilha das câmeras do Digifort lida no formulário (enviada à Galeria ao salvar)
  planilhaNova?: PlanilhaPendente | null;
  // Digifort já cadastrado: o que a Galeria do equipamento já tem (exigência satisfeita sem nova planilha)
  planilhaSalva?: PlanilhaSalvaInfo | null;
}

export interface CameraLidaPlanilha {
  nome: string;
  ip: string;
  modelo: string;
  senha: string;
  situacao: "nova" | "atualiza";
}

// Planilha CSV/XLSX já lida e interpretada, à espera de ser enviada ao equipamento
export interface PlanilhaPendente {
  nomeArquivo: string;
  linhas: string[][];
  linhasBrutas: unknown[][];
  linhaCabecalho: number;
  colunasSenha: number[];
  temOpcaoNomeDescricao: boolean;
  opcaoNome: "descricao" | "nome" | "auto";
  exemploNome?: string;
  exemploDescricao?: string;
  cams: CameraLidaPlanilha[];
}

export interface PlanilhaSalvaInfo {
  nome_arquivo?: string;
  total_linhas?: number;
  importado_em?: string;
  total_cameras: number;
}

// Câmera sincronizada de um NVR (galeria)
export interface NvrCamera {
  id?: string;
  canal: number;
  nome?: string;
  ip?: string | null;
  username?: string | null;
  modelo?: string | null;
  canal_rtsp?: number | null;
  ip_compartilhado?: boolean;
  has_password?: boolean;
  status_comunicacao?: string;
  captura_status?: string;
  captura_motivo?: string;
  captura_horario?: string | null;
  night_image_date?: string | null;
  perfect_image_base64?: string | null;
  night_image_base64?: string | null;
}

export interface PlanilhaVms {
  nome_arquivo: string;
  linha_cabecalho: number;
  total_linhas: number;
  importado_em: string;
  colunas_senha: number[];
  senhas_ocultas: boolean;
  linhas: string[][];
}

export interface AgentLog {
  id: string;
  event_type: string;
  message: string;
  created_at: string | null;
}

export interface AgentVersion {
  id: string;
  version: string;
  url_service: string;
  sha256_service: string;
  url_tray?: string | null;
  sha256_tray?: string | null;
  active: boolean;
}

export interface NVR {
  id: string;
  machine_id?: string;
  tipo: TipoEquipamento;
  name: string;
  ip: string;
  username: string;
  config_extra?: EquipamentoConfig | null;
  last_recording_status?: CameraRecStatus[] | null;
  last_telemetry_status?: NVRTelemetry | null;
  active: boolean;
}

// Alias semântico
export type Equipamento = NVR;

// Máquina: computador com o agente instalado (pertence a no máximo 1 Cliente)
export interface Machine {
  id: string;
  name: string;
  api_key_prefix: string;
  backup_hour: number;
  backup_minute: number;
  email_to: string[];
  zip_password?: string;
  active: boolean;
  last_seen: string | null;
  last_backup_at: string | null;
  last_backup_status: string | null;
  created_at: string;
  nvr_count: number;
  restart_requested?: boolean;
  backup_requested?: boolean;
  telemetry?: Record<string, any> | null;
  api_key?: string; // only on create/rotate
  // Campos calculados no servidor (fonte única da verdade para status online)
  is_online?: boolean;
  current_server_time?: string;
  queue_order?: number;
  customer_id?: string | null;
  customer_name?: string | null;
  // true quando a máquina tem cliente: o horário vem do cliente
  schedule_from_customer?: boolean;
  // true quando a máquina tem cliente: os e-mails do relatório vêm do cliente
  email_from_customer: boolean;
}

export interface NVRResult {
  nome: string;
  status: string;
  tipo?: TipoEquipamento;
  cameras?: CameraRecStatus[];
  telemetria?: NVRTelemetry | null;
}

export interface Backup {
  id: string;
  machine_id?: string;
  machine_name: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  nvr_results: NVRResult[] | null;
  zip_filename: string | null;
  zip_size: number | null;
  email_sent: boolean;
  trigger: string;
  created_at: string | null;
  // Rodada de backup do cliente em que este backup entrou (null = máquina sem cliente)
  run_id?: string | null;
}

export interface PaginatedBackups {
  items: Backup[];
  total: number;
  page: number;
  pages: number;
}

export interface Stats {
  machines_total: number;
  machines_active: number;
  customers_total: number;
  backups_today: number;
  backups_ok: number;
  backups_error: number;
}

export interface Settings {
  smtp_server: string | null;
  smtp_port: string | null;
  smtp_email: string | null;
  retention_days: string | null;
}

// Cliente: a empresa atendida (Cliente → Máquinas → Equipamentos)
export interface Customer {
  id: string;
  name: string;
  description: string | null;
  active: boolean;
  backup_hour: number;
  backup_minute: number;
  // Destinatários do e-mail único por rodada (relatório de todas as máquinas)
  email_to: string[];
  created_at: string;
  machines_total: number;
  machines_online: number;
  health: "ALL_OK" | "PARTIAL" | "ALL_ERROR" | "NO_DATA";
  last_backup_at: string | null;
  queue_active: boolean;
  queue_current_index?: number | null;
  // true quando o cliente tem senha configurada no ZIP do cliente
  has_zip_password: boolean;
  machines: Machine[]; // ordenadas por queue_order
}

// Rodada de backup do cliente: agrupa os backups das máquinas e gera 1 e-mail
export type CustomerRunTrigger = "scheduled" | "queue" | "manual_machine";
// "EM_ANDAMENTO" enquanto aberta; ao fechar: OK, PARCIAL ou ERRO
export type CustomerRunStatus = "EM_ANDAMENTO" | "OK" | "PARCIAL" | "ERRO";

export interface CustomerRunMachine {
  machine_id: string;
  machine_name: string;
  backup_id: string | null;
  // status do backup; "NAO_EXECUTOU" se não reportou e a rodada fechou; null se ainda aberta
  status: string | null;
  zip: boolean;
}

export interface CustomerRun {
  id: string;
  trigger: CustomerRunTrigger | string;
  started_at: string;
  deadline_at: string;
  closed_at: string | null;
  status: CustomerRunStatus | string;
  email_sent: boolean;
  machines_expected: number;
  machines_reported: number;
  machines_ok: number;
  has_zip: boolean;
  machines: CustomerRunMachine[];
}

// ── Multi-contas ──────────────────────────────────────────────
export type Papel = "SUPER_ADMIN" | "ADMIN" | "LEITURA";
export type TipoConta = "INTEGRADOR" | "CLIENTE_FINAL";
export type StatusConta = "OK" | "AVISO" | "CRITICO" | "VENCIDA" | "SUSPENSA" | "VITALICIA";

export interface ContaResumo {
  id: string;
  nome: string;
  tipo: TipoConta;
  plano_nome: string | null;
  expira_em: string | null;
  dias_restantes: number | null;
  status: StatusConta;
  bloqueada: boolean;
  plataforma: boolean;
}

export interface Rotulos {
  grupo_singular: string;
  grupo_plural: string;
}

export interface Me {
  usuario: { id: string | null; nome: string; email: string | null; papel: Papel };
  conta: ContaResumo | null;
  somente_leitura: boolean;
  rotulos: Rotulos;
}

export interface Plano {
  id: string;
  nome: string;
  duracao_dias: number;
  ativo: boolean;
  criado_em: string;
}

export interface Renovacao {
  id: string;
  plano_nome: string;
  dias: number;
  expira_em_anterior: string | null;
  expira_em_nova: string;
  feito_por: string | null;
  criado_em: string;
}

export interface Conta extends ContaResumo {
  documento: string | null;
  email_contato: string | null;
  telefone: string | null;
  observacoes: string | null;
  plano_id: string | null;
  ativo: boolean;
  criado_em: string;
  total_clientes: number;
  total_maquinas: number;
  total_usuarios: number;
}

export interface ContaDetalhe extends Conta {
  renovacoes: Renovacao[];
}

export interface Usuario {
  id: string;
  nome: string;
  email: string;
  papel: Papel;
  ativo: boolean;
  ultimo_login: string | null;
  criado_em: string;
}

