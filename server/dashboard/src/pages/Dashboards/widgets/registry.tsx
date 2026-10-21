import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  LayoutGrid,
  Server,
  ShieldCheck,
  Type,
  Video,
} from "lucide-react";
import {
  Altura,
  DadosCameras,
  DadosEquipamentos,
  DadosHistorico,
  DadosResumo,
  DadosSaudeServidor,
  DadosStatusBackups,
  DadosTexto,
  Largura,
  WidgetInstancia,
} from "../types";
import ResumoWidget from "./ResumoWidget";
import SaudeServidorWidget from "./SaudeServidorWidget";
import StatusBackupsWidget from "./StatusBackupsWidget";
import HistoricoBackupsWidget from "./HistoricoBackupsWidget";
import CamerasWidget from "./CamerasWidget";
import EquipamentosWidget from "./EquipamentosWidget";
import TextoWidget from "./TextoWidget";

export interface DefinicaoWidget {
  tipo: string;
  rotulo: string;
  descricao: string;
  icone: LucideIcon;
  larguraPadrao: Largura;
  alturaPadrao: Altura;
  configPadrao: Record<string, unknown>;
  renderizar: (dados: unknown, widget: WidgetInstancia) => ReactNode;
}

export const DEFINICOES: Record<string, DefinicaoWidget> = {
  resumo: {
    tipo: "resumo",
    rotulo: "Resumo",
    descricao: "Visão geral de máquinas, backups e câmeras do cliente",
    icone: LayoutGrid,
    larguraPadrao: 12,
    alturaPadrao: 1,
    configPadrao: {},
    renderizar: (dados, widget) => {
      // Cast tipado para os dados do resumo
      const d = (dados || {}) as DadosResumo;
      return <ResumoWidget dados={d} widget={widget} />;
    },
  },
  saude_servidor: {
    tipo: "saude_servidor",
    rotulo: "Saúde do servidor",
    descricao: "Medidores de CPU, RAM, disco, rede e GPU das máquinas",
    icone: Activity,
    larguraPadrao: 12,
    alturaPadrao: 3,
    configPadrao: { maquinas: [] },
    renderizar: (dados, widget) => {
      // Cast tipado para os dados de telemetria
      const d = (dados || { maquinas: [] }) as DadosSaudeServidor;
      return <SaudeServidorWidget dados={d} widget={widget} />;
    },
  },
  status_backups: {
    tipo: "status_backups",
    rotulo: "Status dos backups",
    descricao: "Último status de backup por máquina e por equipamento",
    icone: ShieldCheck,
    larguraPadrao: 6,
    alturaPadrao: 2,
    configPadrao: { maquinas: [] },
    renderizar: (dados, widget) => {
      // Cast tipado para status recente de backups
      const d = (dados || { maquinas: [] }) as DadosStatusBackups;
      return <StatusBackupsWidget dados={d} widget={widget} />;
    },
  },
  historico_backups: {
    tipo: "historico_backups",
    rotulo: "Histórico de backups",
    descricao: "Histórico de execuções com taxa de sucesso e duração",
    icone: BarChart3,
    larguraPadrao: 6,
    alturaPadrao: 2,
    configPadrao: { maquinas: [], periodo: null, visual: "grafico" },
    renderizar: (dados, widget) => {
      // Cast tipado para dados históricos
      const d = (dados || { periodo: "7d", dias: [], recentes: [] }) as DadosHistorico;
      return <HistoricoBackupsWidget dados={d} widget={widget} />;
    },
  },
  cameras: {
    tipo: "cameras",
    rotulo: "Câmeras e gravação",
    descricao: "Status de comunicação e gravação das câmeras",
    icone: Video,
    larguraPadrao: 6,
    alturaPadrao: 2,
    configPadrao: { equipamentos: [], apenas_problemas: false },
    renderizar: (dados, widget) => {
      // Cast tipado para monitoramento de câmeras
      const d = (dados || { equipamentos: [] }) as DadosCameras;
      return <CamerasWidget dados={d} widget={widget} />;
    },
  },
  equipamentos: {
    tipo: "equipamentos",
    rotulo: "Equipamentos",
    descricao: "Lista de equipamentos cadastrados por tipo",
    icone: Server,
    larguraPadrao: 6,
    alturaPadrao: 2,
    configPadrao: { tipos: [], maquinas: [] },
    renderizar: (dados, widget) => {
      // Cast tipado para lista de equipamentos
      const d = (dados || { equipamentos: [] }) as DadosEquipamentos;
      return <EquipamentosWidget dados={d} widget={widget} />;
    },
  },
  texto: {
    tipo: "texto",
    rotulo: "Texto",
    descricao: "Bloco de texto livre ou aviso institucional",
    icone: Type,
    larguraPadrao: 4,
    alturaPadrao: 1,
    configPadrao: { texto: "" },
    renderizar: (dados, widget) => {
      // Cast tipado para texto institucional
      const d = (dados || { texto: "" }) as DadosTexto;
      return <TextoWidget dados={d} widget={widget} />;
    },
  },
};

export const definicaoDe = (tipo: string): DefinicaoWidget | undefined =>
  DEFINICOES[tipo];
