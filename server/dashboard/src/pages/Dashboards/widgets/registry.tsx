import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  HardDrive,
  LayoutGrid,
  Network,
  PieChart as IconePizza,
  Server,
  ShieldAlert,
  ShieldCheck,
  Type,
  Video,
  Wifi,
} from "lucide-react";
import {
  Altura,
  DadosAlarmesDefense,
  DadosAntenas,
  DadosCameras,
  DadosStatusOlt,
  DadosEquipamentos,
  DadosHistorico,
  DadosResumo,
  DadosSaudeServidor,
  DadosStatusBackups,
  DadosStatusNvr,
  DadosTelemetriaEquipamentos,
  DadosTexto,
  Largura,
  WidgetInstancia,
} from "../types";
import ResumoWidget from "./ResumoWidget";
import SaudeServidorWidget from "./SaudeServidorWidget";
import StatusBackupsWidget from "./StatusBackupsWidget";
import HistoricoBackupsWidget from "./HistoricoBackupsWidget";
import CamerasWidget from "./CamerasWidget";
import TelemetriaEquipamentosWidget from "./TelemetriaEquipamentosWidget";
import EquipamentosWidget from "./EquipamentosWidget";
import TextoWidget from "./TextoWidget";
import StatusNvrWidget from "./StatusNvrWidget";
import AntenasWidget from "./AntenasWidget";
import StatusOltWidget from "./StatusOltWidget";
import AlarmesDefenseWidget from "./AlarmesDefenseWidget";

export type CampoWidget =
  | { chave: string; tipo: "maquinas"; rotulo: string }
  | { chave: string; tipo: "equipamentos"; rotulo: string; tipos?: string[] }
  | { chave: string; tipo: "tipos"; rotulo: string }
  | { chave: string; tipo: "periodo"; rotulo: string }
  | { chave: string; tipo: "opcao"; rotulo: string; opcoes: { valor: string; rotulo: string }[] }
  | { chave: string; tipo: "booleano"; rotulo: string }
  | { chave: string; tipo: "texto"; rotulo: string; max: number }
  | { chave: string; tipo: "telemetria"; rotulo: string };

export const LARGURAS: { valor: Largura; rotulo: string }[] = [
  { valor: 3, rotulo: "¼" },
  { valor: 4, rotulo: "⅓" },
  { valor: 6, rotulo: "½" },
  { valor: 8, rotulo: "⅔" },
  { valor: 12, rotulo: "Total" },
];

export interface DefinicaoWidget {
  tipo: string;
  rotulo: string;
  descricao: string;
  icone: LucideIcon;
  larguraPadrao: Largura;
  alturaPadrao: Altura;
  larguraMin: number;
  alturaMin: number;
  // Conteúdo que preenche a altura da caixa (gráficos): não é ajustado ao conteúdo
  alturaFluida?: boolean;
  configPadrao: Record<string, unknown>;
  campos: CampoWidget[];
  renderizar: (dados: unknown, widget: WidgetInstancia) => ReactNode;
}

export const DEFINICOES: Record<string, DefinicaoWidget> = {
  resumo: {
    tipo: "resumo",
    rotulo: "Resumo",
    descricao: "Visão geral de máquinas, backups e câmeras do cliente",
    icone: LayoutGrid,
    larguraPadrao: 12,
    alturaPadrao: 3,
    larguraMin: 4,
    alturaMin: 3,
    configPadrao: {},
    campos: [],
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
    alturaPadrao: 9,
    larguraMin: 4,
    alturaMin: 6,
    configPadrao: { maquinas: [] },
    campos: [{ chave: "maquinas", tipo: "maquinas", rotulo: "Máquinas exibidas" }],
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
    alturaPadrao: 6,
    larguraMin: 3,
    alturaMin: 5,
    configPadrao: { maquinas: [] },
    campos: [{ chave: "maquinas", tipo: "maquinas", rotulo: "Máquinas exibidas" }],
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
    alturaPadrao: 6,
    larguraMin: 4,
    alturaMin: 6,
    alturaFluida: true,
    configPadrao: { maquinas: [], periodo: null, visual: "grafico" },
    campos: [
      { chave: "maquinas", tipo: "maquinas", rotulo: "Máquinas exibidas" },
      { chave: "periodo", tipo: "periodo", rotulo: "Período" },
      {
        chave: "visual",
        tipo: "opcao",
        rotulo: "Visual",
        opcoes: [
          { valor: "grafico", rotulo: "Gráfico" },
          { valor: "tabela", rotulo: "Tabela" },
        ],
      },
    ],
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
    alturaPadrao: 6,
    larguraMin: 3,
    alturaMin: 6,
    configPadrao: { equipamentos: [], apenas_problemas: false },
    campos: [
      { chave: "equipamentos", tipo: "equipamentos", rotulo: "Equipamentos exibidos" },
      { chave: "apenas_problemas", tipo: "booleano", rotulo: "Mostrar apenas câmeras com problema" },
    ],
    renderizar: (dados, widget) => {
      // Cast tipado para monitoramento de câmeras
      const d = (dados || { equipamentos: [] }) as DadosCameras;
      return <CamerasWidget dados={d} widget={widget} />;
    },
  },
  telemetria_equipamentos: {
    tipo: "telemetria_equipamentos",
    rotulo: "Gravadores (CPU, RAM e discos)",
    descricao:
      "Telemetria dos gravadores (NVR/DVR) personalizável: escolha CPU, memória, tempo ligado e, por disco, uso, temperatura, saúde, capacidade e idade",
    icone: HardDrive,
    larguraPadrao: 6,
    alturaPadrao: 6,
    larguraMin: 4,
    alturaMin: 7,
    configPadrao: { equipamentos: [], apenas_problemas: false, metricas: [], discos: {} },
    campos: [
      { chave: "equipamentos", tipo: "equipamentos", rotulo: "Gravadores exibidos", tipos: ["NVR"] },
      { chave: "metricas", tipo: "telemetria", rotulo: "O que exibir" },
      { chave: "apenas_problemas", tipo: "booleano", rotulo: "Mostrar apenas gravadores com problema" },
    ],
    renderizar: (dados, widget) => {
      // Cast tipado para telemetria dos gravadores
      const d = (dados || { metricas: [], equipamentos: [] }) as DadosTelemetriaEquipamentos;
      return <TelemetriaEquipamentosWidget dados={d} widget={widget} />;
    },
  },
  equipamentos: {
    tipo: "equipamentos",
    rotulo: "Equipamentos",
    descricao: "Lista de equipamentos cadastrados por tipo",
    icone: Server,
    larguraPadrao: 6,
    alturaPadrao: 6,
    larguraMin: 3,
    alturaMin: 5,
    configPadrao: { tipos: [], maquinas: [] },
    campos: [
      { chave: "tipos", tipo: "tipos", rotulo: "Tipos de equipamento" },
      { chave: "maquinas", tipo: "maquinas", rotulo: "Máquinas exibidas" },
    ],
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
    alturaPadrao: 3,
    larguraMin: 2,
    alturaMin: 2,
    configPadrao: { texto: "" },
    campos: [
      { chave: "texto", tipo: "texto", rotulo: "Texto", max: 1000 },
    ],
    renderizar: (dados, widget) => {
      // Cast tipado para texto institucional
      const d = (dados || { texto: "" }) as DadosTexto;
      return <TextoWidget dados={d} widget={widget} />;
    },
  },
  status_nvr: {
    tipo: "status_nvr",
    rotulo: "Status dos NVRs (pizza)",
    descricao: "Gráfico de pizza com a situação das câmeras de cada NVR: gravando, sem gravação, offline e não verificado",
    icone: IconePizza,
    larguraPadrao: 6,
    alturaPadrao: 8,
    larguraMin: 3,
    alturaMin: 7,
    configPadrao: { equipamentos: [], visual: "por_equipamento" },
    campos: [
      {
        chave: "equipamentos",
        tipo: "equipamentos",
        rotulo: "NVRs exibidos",
        tipos: ["NVR", "DIGIFORT", "DEFENSE"],
      },
      {
        chave: "visual",
        tipo: "opcao",
        rotulo: "Visual",
        opcoes: [
          { valor: "por_equipamento", rotulo: "Uma pizza por NVR" },
          { valor: "agregado", rotulo: "Uma pizza com todos" },
        ],
      },
    ],
    renderizar: (dados, widget) => {
      // Cast tipado para status dos NVRs
      const d = (dados || {
        visual: "por_equipamento",
        total: { total: 0, gravando: 0, sem_gravacao: 0, nao_verificado: 0, offline: 0 },
        equipamentos: [],
      }) as DadosStatusNvr;
      return <StatusNvrWidget dados={d} widget={widget} />;
    },
  },
  antenas: {
    tipo: "antenas",
    rotulo: "Antenas Wi-Fi",
    descricao: "Antenas online e fora do ar (com há quanto tempo), problemas primeiro",
    icone: Wifi,
    larguraPadrao: 6,
    alturaPadrao: 6,
    larguraMin: 3,
    alturaMin: 3,
    configPadrao: { equipamentos: [], mostrar_latencia: true },
    campos: [
      { chave: "equipamentos", tipo: "equipamentos", rotulo: "Equipamentos de antenas exibidos", tipos: ["ANTENA"] },
      { chave: "mostrar_latencia", tipo: "booleano", rotulo: "Mostrar a latência (ping) das antenas online" },
    ],
    renderizar: (dados, widget) => {
      const d = (dados || { mostrar_latencia: true, total: { total: 0, online: 0, offline: 0, sem_registro: 0, erro: 0 }, equipamentos: [] }) as DadosAntenas;
      return <AntenasWidget dados={d} widget={widget} />;
    },
  },
  status_olt: {
    tipo: "status_olt",
    rotulo: "OLTs e ONUs",
    descricao: "ONUs online, fora do ar e com sinal ruim por OLT, PONs com problema e licença da UNM2000",
    icone: Network,
    larguraPadrao: 6,
    alturaPadrao: 7,
    larguraMin: 3,
    alturaMin: 3,
    configPadrao: { equipamentos: [], mostrar_pons: true, mostrar_licenca: true },
    campos: [
      { chave: "equipamentos", tipo: "equipamentos", rotulo: "OLTs exibidas", tipos: ["OLT"] },
      { chave: "mostrar_pons", tipo: "booleano", rotulo: "Mostrar as PONs com problema" },
      { chave: "mostrar_licenca", tipo: "booleano", rotulo: "Mostrar a licença da UNM2000" },
    ],
    renderizar: (dados, widget) => {
      const d = (dados || {
        total: { total: 0, online: 0, offline: 0, falha: 0, sem_energia: 0, sinal_ruim: 0 },
        equipamentos: [],
      }) as DadosStatusOlt;
      return <StatusOltWidget dados={d} widget={widget} />;
    },
  },
  alarmes_defense: {
    tipo: "alarmes_defense",
    rotulo: "Centrais de alarme",
    descricao: "Disparos, centrais desconectadas e partições das centrais de alarme do Defense",
    icone: ShieldAlert,
    larguraPadrao: 6,
    alturaPadrao: 6,
    larguraMin: 3,
    alturaMin: 3,
    configPadrao: { equipamentos: [], mostrar_particoes: true, mostrar_incendio: true },
    campos: [
      { chave: "equipamentos", tipo: "equipamentos", rotulo: "Equipamentos Defense exibidos", tipos: ["DEFENSE"] },
      { chave: "mostrar_particoes", tipo: "booleano", rotulo: "Mostrar as partições (armada/desarmada só aparece no painel, não no link público)" },
      { chave: "mostrar_incendio", tipo: "booleano", rotulo: "Mostrar as centrais de incêndio" },
    ],
    renderizar: (dados, widget) => {
      const d = (dados || { mostra_armada: false, total: { centrais: 0, desconectadas: 0, disparos: 0 }, equipamentos: [] }) as DadosAlarmesDefense;
      return <AlarmesDefenseWidget dados={d} widget={widget} />;
    },
  },
};

export const definicaoDe = (tipo: string): DefinicaoWidget | undefined =>
  DEFINICOES[tipo];
