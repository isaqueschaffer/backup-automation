export type TipoEquipamento = "NVR" | "OLT" | "ONU" | "PABX" | "MIKROTIK" | "DIGIFORT" | "DEFENSE" | "CAMERA" | "ANTENA" | "MIXED";

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
  porta_alarme?: number;
  olts?: string;
  telnet_usuario?: string;
  telnet_senha_definida?: boolean;
  telnet_enable_definida?: boolean;
  nomes_db_host?: string;
  nomes_db_usuario?: string;
  nomes_db_nome?: string;
  licenca_inicio?: string;
  licenca_fim?: string;
  nomes_db_senha_definida?: boolean;
  // ANTENA: acesso SSH ao MikroTik (porta), prefixos de fabricante da busca automática e as antenas cadastradas
  porta_ssh?: number;
  prefixos_mac?: string;
  antenas?: AntenaCadastro[];
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
  porta_alarme?: number | string;
  olts?: string;
  telnet_usuario?: string;
  telnet_senha?: string;
  telnet_enable?: string;
  telnet_senha_definida?: boolean;
  nomes_db_host?: string;
  nomes_db_usuario?: string;
  nomes_db_senha?: string;
  nomes_db_senha_definida?: boolean;
  licenca_inicio?: string;
  licenca_fim?: string;
  // ANTENA
  porta_ssh?: number | string;
  prefixos_mac?: string;
  antenas?: AntenaCadastro[];
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
  // Subpasta de gravação desta câmera (coluna "Diretório de gravação" do export do Digifort)
  pastaGravacao?: string;
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
  // Raiz comum dos caminhos da coluna "Diretório de gravação" (vazio se a planilha não tiver essa coluna)
  raizGravacoes?: string;
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
  offline_segundos?: number | null;
  offline_aprox?: boolean;
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
  nivel: "INFO" | "WARNING" | "ERROR";
  equipamento: string | null;
  created_at: string | null;
}

export interface AgentVersion {
  id: string;
  version: string;
  url_service: string;
  sha256_service: string;
  url_tray?: string | null;
  sha256_tray?: string | null;
  url_linux?: string | null;     // pacote do agente Linux/Mikrotik (>= 1.1.52)
  sha256_linux?: string | null;
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
  conexao_status?: ConexaoStatus | null;
  active: boolean;
}

// "Testar conexão": etapas executadas pelo agente na máquina
export type EstadoEtapaConexao = "pendente" | "andamento" | "ok" | "erro" | "pulado";
export interface EtapaConexao {
  id: string;
  rotulo: string;
  estado: EstadoEtapaConexao;
  detalhe?: string | null;
}
export interface ConexaoTeste {
  task_id: string | null;
  equipamento_id: string;
  etapas: EtapaConexao[];
  concluido: boolean;
  ok: boolean | null;
  mensagem: string | null;
  segundos: number;
}
// Último teste gravado no equipamento (testado_em: naive em UTC, REGRA-001)
export interface ConexaoStatus {
  ok: boolean;
  mensagem: string | null;
  etapas: EtapaConexao[];
  segundos: number;
  testado_em: string;
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
  agent_version?: string | null; // informada pelo agente no ping (>= 1.1.49)
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

export interface AuditoriaItem {
  id: string;
  created_at: string;
  usuario: string;
  message: string;
  equipamento: string | null;
  machine_id: string;
  machine_name: string | null;
  customer_id: string | null;
  customer_name: string | null;
}

export interface PaginatedAuditoria {
  items: AuditoriaItem[];
  total: number;
  page: number;
  pages: number;
  dias_retencao: number;
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


// Status das OLTs de uma UNM2000, enviado pelo agente por SNMP (GET /machines/{id}/equipamentos/{id}/olt-status)
export interface OltOnu {
  indice: string;
  slot: number | null;
  pon: number | null;
  onu?: number;
  tipo?: string | null;
  serial?: string | null;
  nome?: string | null;
  mac?: string | null;
  temperatura_onu?: number;
  sinal_olt_dbm?: number;
  sinal_onu_dbm?: number;
  qualidade?: "BOM" | "ATENCAO" | "RUIM" | null;
  medido_em?: string;
  estado: "ONLINE" | "OFFLINE" | "FALHA" | "SEM_ENERGIA" | "DESCONHECIDO";
}

export interface OltPonResumo {
  slot: number | null;
  pon: number | null;
  total: number;
  online: number;
  offline: number;
  falha: number;
  sem_energia: number;
  sinal_ruim?: number;
  tx_dbm?: number | null;
  temperatura_gbic?: number | null;
}

export interface OltPlaca {
  slot: number | null;
  tipo?: string | null;
  hardware?: string | null;
  software?: string | null;
  status?: string | null;
  portas?: number | null;
  portas_livres?: number | null;
  cpu_percent?: number | null;
  memoria_percent?: number | null;
}

export interface OltStatus {
  nome: string;
  ip: string;
  erro?: string;
  fabricante?: string | null;
  coletado_em?: string;
  firmware?: string | null;
  hardware?: string | null;
  nomes?: { com_nome: number; sem_nome: number; erro?: string } | null;
  modelo?: string | null;
  controladora?: { slot: number; tipo?: string | null; software?: string | null } | null;
  temperatura?: number | null;
  total_onus_olt?: number | null;
  totais?: { total: number; online: number; offline: number; falha: number; sem_energia: number; sinal_ruim?: number };
  por_pon?: OltPonResumo[];
  placas?: OltPlaca[];
  interfaces_pon?: { nome: string; ativa: boolean }[];
  onus?: OltOnu[];
}

export interface OltStatusResponse {
  atualizado_em: string | null;
  olts: OltStatus[];
  licenca?: { inicio: string | null; fim: string; dias_restantes: number } | null;
}

// ─── Alarmes (DEFENSE) ────────────────────────────────────────────────────
export interface AlarmPartition {
  id?: number | string | null;
  nome: string;
  armada: boolean;
  disparada?: boolean;
}

export interface AlarmCentral {
  id?: number | string | null;
  nome: string;
  modelo?: string | null;
  status?: number | null;
  particoes: AlarmPartition[];
}

export interface CentralIncendio {
  id?: number | string | null;
  nome: string;
  modelo?: string | null;
  status?: number | null;
}

export interface AlarmeStatusResponse {
  atualizado_em: string | null;
  ip?: string | null;
  erro?: string | null;
  alarmes: AlarmCentral[];
  incendio?: CentralIncendio[];
}

// ─── Notificações ───────────────────────────────────────────────────────────
export type TipoNotificacao = "LICENCA_UNM2000" | "BACKUP_FALHOU" | "AGENTE_OFFLINE" | "PERSONALIZADA" | "CAMERA_OFFLINE" | "ALARME" | "ANTENA_OFFLINE";
export type ModoNotificacaoPersonalizada = "RECORRENTE" | "DATA";

export interface Notificacao {
  id: string;
  tipo: TipoNotificacao;
  titulo: string;
  mensagem: string;
  machine_id?: string | null;
  nvr_id?: string | null;
  camera_id?: string | null;
  definicao_id?: string | null;
  criado_em: string;
  atualizado_em: string;
}

// Opt-in por câmera (CAMERA_OFFLINE): NVR, DIGIFORT e DEFENSE
export interface CameraNotificacao {
  id: string;
  nome: string;
  notificar_offline: boolean;
  status_comunicacao?: string | null;
  offline_segundos?: number | null;
  offline_aprox?: boolean;
}

export interface EquipamentoCamerasNotificacao {
  nvr_id: string;
  nvr_nome: string;
  nvr_tipo: string;
  machine_id: string;
  machine_nome: string;
  cameras: CameraNotificacao[];
}

export interface CentralAlarmeNotificacao {
  central_id: string;
  nome: string;
  conectada: boolean;
  disparada: boolean;
  particoes_total: number;
  particoes_desarmadas: number;
  notificar: boolean;
}

export interface EquipamentoAlarmesNotificacao {
  nvr_id: string;
  nvr_nome: string;
  machine_id: string;
  machine_nome: string;
  atualizado_em?: string | null;
  erro?: string | null;
  centrais: CentralAlarmeNotificacao[];
}

export interface NotificacaoPersonalizada {
  id: string;
  titulo: string;
  mensagem: string;
  enviar_email: boolean;
  mostrar_popup: boolean;
  ativo: boolean;
  modo: ModoNotificacaoPersonalizada;
  intervalo_dias?: number | null;
  data_alvo?: string | null;
  dias_antes?: number | null;
  ultimo_disparo_em?: string | null;
  criado_em: string;
  atualizado_em: string;
}

export interface NotificacaoPersonalizadaPayload {
  titulo: string;
  mensagem: string;
  enviar_email: boolean;
  mostrar_popup: boolean;
  ativo: boolean;
  modo: ModoNotificacaoPersonalizada;
  intervalo_dias?: number | null;
  data_alvo?: string | null;
  dias_antes?: number | null;
}

export interface ConfiguracaoNotificacao {
  tipo: TipoNotificacao;
  ativo: boolean;
}

// ── Antenas (equipamento ANTENA): lidas pelo MikroTik por SSH (GET /machines/{id}/equipamentos/{id}/antena-status)
export interface AntenaCadastro {
  nome: string;
  mac: string;
  ip?: string;
  // Marca informada pelo usuário (vale sobre a detectada pelo LLDP/vizinho)
  marca?: string;
  notificar?: boolean;
}

export type SituacaoAntena = "ONLINE" | "OFFLINE" | "SEM_REGISTRO" | "ERRO";

export interface AntenaStatus {
  nome: string;
  mac: string;
  ip?: string;
  ip_ultimo?: boolean;
  mac_visto?: string;
  hostname?: string;
  interface?: string;
  fontes?: string[];
  arp_status?: string;
  ping_ms?: number | null;
  // Marca em uso (a do cadastro ou, sem ela, a detectada) e a que o LLDP/vizinho/DHCP anunciou
  marca?: string;
  marca_detectada?: string;
  status: SituacaoAntena;
  notificar?: boolean;
  erro?: string;
  ultimo_online?: string | null;
  offline_desde?: string | null;
}

export interface AntenaDescoberta {
  mac: string;
  ip?: string;
  hostname?: string;
  interface?: string;
  fontes?: string[];
  motivo?: string;
  marca?: string;
  macs?: string[];
}

export interface AntenaStatusResponse {
  atualizado_em: string | null;
  erro: string | null;
  mikrotik: { identidade?: string; ip?: string; dispositivos?: number };
  antenas: AntenaStatus[];
  descobertas: AntenaDescoberta[];
}
