export type Periodo = "24h" | "7d" | "30d";
export type Largura = number;
export type Altura = number;
// Grade do schema 3: 24 colunas e linhas de 31 px. Cada linha já inclui o espaço entre os
// cartões (o item tem 6 px de respiro em cada lado), então 2 linhas = 1 linha antiga de 50 px + 12 px.
export const COLUNAS_GRADE = 24;
export const ALTURA_LINHA_PX = 31;
export const RESPIRO_GRADE_PX = 6;
export const ALTURA_MAX_GRADE = 80;
export type TipoWidget =
  | "resumo"
  | "saude_servidor"
  | "status_backups"
  | "historico_backups"
  | "cameras"
  | "telemetria_equipamentos"
  | "equipamentos"
  | "texto"
  | "status_nvr"
  | "antenas"
  | "status_olt"
  | "alarmes_defense";

export interface WidgetInstancia {
  id: string;
  tipo: string;
  titulo: string | null;
  x: number;
  y: number;
  largura: Largura;
  altura: Altura;
  config: Record<string, unknown>;
}

export interface DashboardLayout {
  schema_version: number;
  filtros: { periodo: Periodo };
  widgets: WidgetInstancia[];
}

export interface DadosWidget {
  ok: boolean;
  dados?: unknown;
  erro?: string;
}

export interface DadosDashboard {
  gerado_em: string;
  widgets: Record<string, DadosWidget>;
}

export interface DashboardPublico {
  cliente_nome: string;
  layout: DashboardLayout;
  version: number;
  pode_editar: boolean;
  dados: DadosDashboard;
}

export interface OpcaoMaquina {
  id: string;
  nome: string;
}

export interface OpcaoEquipamento {
  id: string;
  nome: string;
  tipo: string;
  maquina_id: string;
  maquina: string;
  discos?: string[];
}

export interface OpcoesDashboard {
  maquinas: OpcaoMaquina[];
  equipamentos: OpcaoEquipamento[];
}

export interface Compartilhamento {
  ativo: boolean;
  tem_link: boolean;
  expira_em: string | null;
  permite_edicao: boolean;
  criado_em: string | null;
  ultimo_acesso: string | null;
  expirado: boolean;
}

export interface DashboardAdmin {
  id: string;
  customer_id: string;
  cliente_nome: string;
  layout: DashboardLayout;
  version: number;
  atualizado_em: string;
  compartilhamento: Compartilhamento;
}

export interface LinkGerado {
  token: string;
  caminho: string;
  url: string | null;
  compartilhamento: Compartilhamento;
}

export interface TipoWidgetCatalogo {
  tipo: string;
  rotulo: string;
  descricao: string;
  largura_padrao: Largura;
  altura_padrao: Altura;
  config_schema: Record<string, unknown>;
}

export interface DadosResumo {
  maquinas_total: number;
  maquinas_online: number;
  maquinas_offline: number;
  backups_ok: number;
  backups_com_falha: number;
  sem_backup: number;
  equipamentos_total: number;
  cameras_total: number;
  cameras_online: number;
  cameras_offline: number;
  cameras_sem_gravacao: number;
  gravadores_com_telemetria: number;
  discos_total: number;
  discos_com_problema: number;
  antenas_total?: number;
  antenas_online?: number;
}

export interface DadosTelemetriaEquipamentos {
  metricas?: string[];
  equipamentos: {
    id: string;
    nome: string;
    tipo: string;
    maquina: string;
    atualizado_em: string | null;
    cpu_percent: number | null;
    ram_percent: number | null;
    uptime_seconds: number | null;
    disks: {
      device?: string;
      status?: string | null;
      percent?: number | null;
      total_gb?: number | null;
      free_gb?: number | null;
      power_on_days?: number | null;
      temperature_c?: number | null;
    }[];
    tem_problema: boolean;
  }[];
}

export interface DadosSaudeServidor {
  maquinas: {
    id: string;
    nome: string;
    online: boolean;
    ultimo_contato: string | null;
    segundos_desde_contato: number | null;
    telemetria: Record<string, unknown> | null;
  }[];
}

export interface DadosStatusBackups {
  maquinas: {
    id: string;
    nome: string;
    status: string | null;
    ultimo_backup: string | null;
    equipamentos: {
      nome: string;
      tipo: string;
      status: string | null;
    }[];
  }[];
}

export interface DadosHistorico {
  periodo: Periodo;
  dias: {
    data: string;
    ok: number;
    parcial: number;
    erro: number;
  }[];
  recentes: {
    maquina: string;
    inicio: string | null;
    fim: string | null;
    status: string;
    duracao_s: number | null;
  }[];
}

export interface DadosCameras {
  equipamentos: {
    id: string;
    nome: string;
    tipo: string;
    maquina: string;
    total: number;
    online: number;
    offline: number;
    sem_gravacao: number;
    cameras: {
      nome: string;
      comunicacao: string;
      gravacao: string | null;
      offline_segundos?: number | null;
      offline_aprox?: boolean;
    }[];
  }[];
}

export interface DadosEquipamentos {
  equipamentos: {
    id: string;
    nome: string;
    tipo: string;
    maquina: string;
    status: string | null;
  }[];
}

export interface DadosTexto {
  texto: string;
}

export interface ContagemStatusCameras {
  total: number;
  gravando: number;
  sem_gravacao: number;
  nao_verificado: number;
  offline: number;
}

export interface DadosStatusNvr {
  visual: "por_equipamento" | "agregado";
  total: ContagemStatusCameras;
  equipamentos: ({ id: string; nome: string; tipo: string; maquina: string } & ContagemStatusCameras)[];
}

// Cor de cada item dos status periódicos (ANTENA, OLT, DEFENSE), calculada no servidor
export type NivelStatus = "critico" | "atencao" | "ok" | "neutro";

export interface AtualidadeStatus {
  id: string;
  nome: string;
  maquina: string;
  atualizado_em: string | null;
  segundos_desde_atualizacao: number | null;
  desatualizado: boolean;
  sem_status: boolean;
  nivel: NivelStatus;
}

export interface DadosAntenas {
  mostrar_latencia: boolean;
  total: { total: number; online: number; offline: number; sem_registro: number; erro: number };
  equipamentos: (AtualidadeStatus & {
    falha_leitura: boolean;
    total: number;
    online: number;
    antenas: {
      nome: string;
      marca: string | null;
      status: "ONLINE" | "OFFLINE" | "SEM_REGISTRO" | "ERRO";
      nivel: NivelStatus;
      ping_ms?: number | null;
      fora_segundos: number | null;
      ultimo_online: string | null;
    }[];
  })[];
}

export interface ContagemOnus {
  total: number;
  online: number;
  offline: number;
  falha: number;
  sem_energia: number;
  sinal_ruim: number;
}

export interface DadosStatusOlt {
  total: ContagemOnus;
  equipamentos: (AtualidadeStatus & {
    licenca: { fim: string; dias_restantes: number; nivel: NivelStatus } | null;
    olts: {
      nome: string;
      fabricante: string | null;
      modelo: string | null;
      falha_leitura: boolean;
      temperatura: number | null;
      totais: ContagemOnus;
      percentual_fora: number;
      pons: ({ slot: number; pon: number } & ContagemOnus)[];
      pons_com_problema: number;
      nivel: NivelStatus;
    }[];
  })[];
}

export interface DadosAlarmesDefense {
  mostra_armada: boolean;
  total: { centrais: number; desconectadas: number; disparos: number };
  equipamentos: (AtualidadeStatus & {
    falha_leitura: boolean;
    centrais: {
      nome: string;
      modelo: string | null;
      conectada: boolean;
      disparos: number;
      nivel: NivelStatus;
      particoes: { nome: string; disparada: boolean; armada?: boolean }[];
    }[];
    incendio: { nome: string; modelo: string | null }[];
  })[];
}
