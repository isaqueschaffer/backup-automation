export type Periodo = "24h" | "7d" | "30d";
export type Largura = 3 | 4 | 6 | 8 | 12;
export type Altura = 1 | 2 | 3 | 4;
export type TipoWidget =
  | "resumo"
  | "saude_servidor"
  | "status_backups"
  | "historico_backups"
  | "cameras"
  | "telemetria_equipamentos"
  | "equipamentos"
  | "texto";

export interface WidgetInstancia {
  id: string;
  tipo: string;
  titulo: string | null;
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
}

export interface DadosTelemetriaEquipamentos {
  equipamentos: {
    id: string;
    nome: string;
    tipo: string;
    maquina: string;
    atualizado_em: string | null;
    cpu_percent: number | null;
    ram_percent: number | null;
    disks: { device?: string; status?: string | null; percent?: number | null; total_gb?: number | null; free_gb?: number | null }[];
    tem_problema: boolean;
  }[];
}

export interface DadosSaudeServidor {
  maquinas: {
    id: string;
    nome: string;
    online: boolean;
    ultimo_contato: string | null;
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
