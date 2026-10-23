import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Eye,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  SlidersHorizontal,
} from "lucide-react";
import { useToast } from "../../components/Toast";
import { apiErrorMessage } from "../../utils/errors";
import {
  ALTURA_LINHA_PX,
  DadosDashboard,
  DashboardLayout,
  GAP_GRADE_PX,
  OpcoesDashboard,
  Periodo,
} from "./types";
import { DefinicaoWidget, definicaoDe } from "./widgets/registry";
import { useDashboardDraft } from "./useDashboardDraft";
import DashboardCanvas from "./DashboardCanvas";
import WidgetAcoesEdicao from "./WidgetAcoesEdicao";
import AddWidgetModal from "./AddWidgetModal";
import WidgetConfigModal from "./WidgetConfigModal";

interface Props {
  layout: DashboardLayout;
  version: number;
  dadosVivos: DadosDashboard | null;
  podeEditar: boolean;
  carregarOpcoes: () => Promise<OpcoesDashboard>;
  previa: (layout: DashboardLayout) => Promise<DadosDashboard>;
  salvar: (
    layout: DashboardLayout,
    version: number
  ) => Promise<{ layout: DashboardLayout; version: number }>;
  restaurar?: () => Promise<{ layout: DashboardLayout; version: number }>;
  onSalvo: (r: { layout: DashboardLayout; version: number }) => void;
  onConflito: () => void;
  barraExtra?: ReactNode;
}

function extrairErro(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { detail?: unknown } } };
  const detail = e?.response?.data?.detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const primeiro = detail[0] as { msg?: unknown };
    if (typeof primeiro?.msg === "string" && primeiro.msg) {
      return primeiro.msg;
    }
  }
  return apiErrorMessage(err, fallback);
}

// Workspace completo de visualização e edição de dashboard
export default function DashboardWorkspace({
  layout,
  version,
  dadosVivos,
  podeEditar,
  carregarOpcoes,
  previa,
  salvar,
  restaurar,
  onSalvo,
  onConflito,
  barraExtra,
}: Props) {
  const { toast } = useToast();

  const [modo, setModo] = useState<"ver" | "editar" | "previa">("ver");
  const [opcoes, setOpcoes] = useState<OpcoesDashboard | null>(null);
  const [dadosPrevia, setDadosPrevia] = useState<DadosDashboard | null>(null);
  const [modalAdicionar, setModalAdicionar] = useState(false);
  const [widgetEmConfig, setWidgetEmConfig] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const opcoesCarregadas = useRef(false);

  const {
    draft,
    dirty,
    adicionar,
    remover,
    mover,
    atualizar,
    setPeriodo,
    descartar,
  } = useDashboardDraft(layout);

  // Carrega opções uma única vez ao entrar em edição ou prévia
  useEffect(() => {
    if (modo === "ver") return;
    if (opcoesCarregadas.current) return;
    opcoesCarregadas.current = true;
    carregarOpcoes()
      .then((op) => setOpcoes(op))
      .catch(() => {
        toast("Erro ao carregar opções para configuração.", "error");
      });
  }, [modo, carregarOpcoes, toast]);

  // Atualiza os dados de prévia do rascunho com debounce de 600 ms
  useEffect(() => {
    if (modo === "ver") return;

    let cancelado = false;
    const timer = setTimeout(() => {
      previa(draft)
        .then((res) => {
          if (!cancelado) {
            setDadosPrevia(res);
          }
        })
        .catch(() => {
          if (!cancelado) {
            toast("Não foi possível atualizar a prévia dos dados.", "info");
          }
        });
    }, 600);

    return () => {
      cancelado = true;
      clearTimeout(timer);
    };
  }, [draft, modo, previa, toast]);

  // Alerta ao tentar fechar a aba com rascunho não salvo
  useEffect(() => {
    if (!dirty || modo === "ver") return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => {
      window.removeEventListener("beforeunload", handler);
    };
  }, [dirty, modo]);

  const handleDescartar = () => {
    if (dirty) {
      if (!confirm("Descartar alterações não salvas?")) return;
    }
    descartar();
    setModo("ver");
  };

  const handleSalvar = async () => {
    setSalvando(true);
    try {
      const res = await salvar(draft, version);
      onSalvo(res);
      toast("Dashboard salvo.", "success");
      setModo("ver");
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        const msg = apiErrorMessage(
          err,
          "O dashboard foi alterado por outra pessoa. Recarregue antes de salvar."
        );
        toast(msg, "error");
        descartar();
        setModo("ver");
        onConflito();
      } else {
        toast(extrairErro(err, "Erro ao salvar o dashboard."), "error");
      }
    } finally {
      setSalvando(false);
    }
  };

  const handleRestaurar = async () => {
    if (!restaurar) return;
    if (!confirm("Restaurar o layout padrão? Suas alterações não salvas serão perdidas.")) {
      return;
    }
    setSalvando(true);
    try {
      const res = await restaurar();
      onSalvo(res);
      toast("Layout padrão restaurado.", "success");
      setModo("ver");
    } catch (err: unknown) {
      toast(extrairErro(err, "Erro ao restaurar layout padrão."), "error");
    } finally {
      setSalvando(false);
    }
  };

  const handleEscolherWidget = (def: DefinicaoWidget) => {
    const novo = adicionar(def);
    setModalAdicionar(false);
    if (def.campos && def.campos.length > 0) {
      setWidgetEmConfig(novo.id);
    }
  };

  const widgetConfigurando = useMemo(
    () => draft.widgets.find((w) => w.id === widgetEmConfig) || null,
    [draft.widgets, widgetEmConfig]
  );

  const ajustarAoConteudo = useCallback(
    (id: string) => {
      const item = document.querySelector<HTMLElement>(`[data-widget-id="${id}"]`);
      if (!item) return;
      const corpo = item.querySelector<HTMLElement>("[data-widget-corpo]");
      if (!corpo) return;

      const widget = draft.widgets.find((w) => w.id === id);
      if (!widget) return;
      const def = definicaoDe(widget.tipo);
      const minA = Math.max(1, def?.alturaMin ?? 1);

      const precisa = corpo.scrollHeight + (item.clientHeight - corpo.clientHeight);
      const linhasCalculadas = Math.ceil(
        (precisa + GAP_GRADE_PX) / (ALTURA_LINHA_PX + GAP_GRADE_PX)
      );
      const linhas = Math.max(minA, Math.min(40, linhasCalculadas));

      atualizar(id, { altura: linhas });
    },
    [draft.widgets, atualizar]
  );

  return (
    <div>
      {/* Barra superior de ações */}
      {modo === "ver" && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
            marginBottom: 16,
          }}
        >
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {podeEditar && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setModo("editar")}
              >
                <SlidersHorizontal size={14} style={{ flexShrink: 0 }} /> Personalizar
              </button>
            )}
          </div>
          {barraExtra && (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {barraExtra}
            </div>
          )}
        </div>
      )}

      {modo === "editar" && (
        <div
          className="card"
          style={{
            padding: "10px 14px",
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            marginBottom: 16,
          }}
        >
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: 8,
            }}
          >
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setModalAdicionar(true)}
            >
              <Plus size={14} style={{ flexShrink: 0 }} /> Adicionar componente
            </button>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: 13,
              }}
            >
              <span style={{ color: "var(--text-secondary)" }}>Período:</span>
              <select
                className="form-input"
                style={{
                  width: "auto",
                  padding: "4px 8px",
                  fontSize: 12,
                  height: "auto",
                }}
                value={draft.filtros?.periodo || "7d"}
                onChange={(e) => setPeriodo(e.target.value as Periodo)}
              >
                <option value="24h">Últimas 24 horas</option>
                <option value="7d">Últimos 7 dias</option>
                <option value="30d">Últimos 30 dias</option>
              </select>
            </div>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setModo("previa")}
            >
              <Eye size={14} style={{ flexShrink: 0 }} /> Prévia
            </button>

            {restaurar && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleRestaurar}
                disabled={salvando}
              >
                <RotateCcw size={14} style={{ flexShrink: 0 }} /> Restaurar padrão
              </button>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleDescartar}
              disabled={salvando}
            >
              Descartar
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSalvar}
              disabled={!dirty || salvando}
            >
              {salvando ? (
                <span className="spinner spinner-sm" />
              ) : (
                <Save size={14} style={{ flexShrink: 0 }} />
              )}{" "}
              Salvar
            </button>
          </div>
        </div>
      )}

      {modo === "previa" && (
        <div
          className="card"
          style={{
            padding: "10px 14px",
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            marginBottom: 16,
            background: "var(--surface-2)",
            borderColor: "var(--border-accent)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 13,
              color: "var(--text-primary)",
            }}
          >
            <Eye size={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
            <span>Prévia — alterações ainda não salvas</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setModo("editar")}
            >
              <Pencil size={14} style={{ flexShrink: 0 }} /> Voltar a editar
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSalvar}
              disabled={salvando}
            >
              {salvando ? (
                <span className="spinner spinner-sm" />
              ) : (
                <Save size={14} style={{ flexShrink: 0 }} />
              )}{" "}
              Salvar
            </button>
          </div>
        </div>
      )}

      {/* Grade de exibição dos componentes */}
      <DashboardCanvas
        layout={modo === "ver" ? layout : draft}
        dados={modo === "ver" ? dadosVivos : (dadosPrevia ?? dadosVivos)}
        editando={modo === "editar"}
        onMover={mover}
        onRedimensionar={modo === "editar" ? (id, t) => atualizar(id, t) : undefined}
        onAjustar={modo === "editar" ? ajustarAoConteudo : undefined}
        renderAcoes={
          modo === "editar"
            ? (w) => (
                <WidgetAcoesEdicao
                  widget={w}
                  onLarguraTotal={() => atualizar(w.id, { largura: 12 })}
                  onAjustar={() => ajustarAoConteudo(w.id)}
                  onConfigurar={() => setWidgetEmConfig(w.id)}
                  onRemover={() => remover(w.id)}
                />
              )
            : undefined
        }
      />

      {/* Modais de adição e configuração */}
      {modalAdicionar && (
        <AddWidgetModal
          onEscolher={handleEscolherWidget}
          onClose={() => setModalAdicionar(false)}
        />
      )}

      {widgetConfigurando && (
        <WidgetConfigModal
          widget={widgetConfigurando}
          opcoes={opcoes}
          onSalvar={(patch) => {
            atualizar(widgetConfigurando.id, patch);
            setWidgetEmConfig(null);
          }}
          onClose={() => setWidgetEmConfig(null)}
        />
      )}
    </div>
  );
}
