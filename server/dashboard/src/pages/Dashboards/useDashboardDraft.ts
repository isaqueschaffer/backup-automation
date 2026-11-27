import { useCallback, useEffect, useMemo, useState } from "react";
import { DashboardLayout, Periodo, WidgetInstancia } from "./types";
import { DefinicaoWidget } from "./widgets/registry";
import { compactar, posicionar, primeiroLugarLivre } from "./gradeLayout";

const LIMITE_HISTORICO = 100;

interface Historico {
  passado: DashboardLayout[];
  atual: DashboardLayout;
  futuro: DashboardLayout[];
}

type PatchWidget = Partial<
  Pick<WidgetInstancia, "titulo" | "x" | "y" | "largura" | "altura" | "config">
>;

const novoHistorico = (layout: DashboardLayout): Historico => ({
  passado: [],
  atual: layout,
  futuro: [],
});

// Gerencia o rascunho de um dashboard em edição, com desfazer/refazer.
// Cada alteração vira um passo do histórico; arrastar e redimensionar só gravam ao soltar.
export function useDashboardDraft(salvo: DashboardLayout) {
  const [hist, setHist] = useState<Historico>(() => novoHistorico(salvo));

  useEffect(() => {
    setHist(novoHistorico(salvo));
  }, [salvo]);

  const draft = hist.atual;

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(salvo),
    [draft, salvo]
  );

  const aplicar = useCallback(
    (fn: (l: DashboardLayout) => DashboardLayout, semHistorico = false) => {
      setHist((prev) => {
        const novo = fn(prev.atual);
        if (novo === prev.atual) return prev;
        if (semHistorico) return { ...prev, atual: novo };
        return {
          passado: [...prev.passado, prev.atual].slice(-LIMITE_HISTORICO),
          atual: novo,
          futuro: [],
        };
      });
    },
    []
  );

  const adicionar = useCallback(
    (def: DefinicaoWidget): WidgetInstancia => {
      let id = "";
      do {
        id = `${def.tipo}-${Math.random().toString(36).slice(2, 8)}`;
      } while (draft.widgets.some((w) => w.id === id));

      const { x, y } = primeiroLugarLivre(draft.widgets, def.larguraPadrao, def.alturaPadrao);
      const novo: WidgetInstancia = {
        id,
        tipo: def.tipo,
        titulo: null,
        x,
        y,
        largura: def.larguraPadrao,
        altura: def.alturaPadrao,
        config: structuredClone(def.configPadrao),
      };

      aplicar((prev) => ({
        ...prev,
        widgets: compactar([...prev.widgets, novo]),
      }));

      return novo;
    },
    [draft.widgets, aplicar]
  );

  const remover = useCallback(
    (id: string) => {
      aplicar((prev) => ({
        ...prev,
        widgets: compactar(prev.widgets.filter((w) => w.id !== id)),
      }));
    },
    [aplicar]
  );

  // Troca as posições de uma vez (resultado de um arrasto ou redimensionamento)
  const definirWidgets = useCallback(
    (widgets: WidgetInstancia[]) => {
      aplicar((prev) => ({ ...prev, widgets }));
    },
    [aplicar]
  );

  const atualizar = useCallback(
    (id: string, patch: PatchWidget, opcoes?: { semHistorico?: boolean }) => {
      aplicar((prev) => {
        const atual = prev.widgets.find((w) => w.id === id);
        if (!atual) return prev;
        const mudaCaixa =
          patch.x !== undefined ||
          patch.y !== undefined ||
          patch.largura !== undefined ||
          patch.altura !== undefined;
        const { x, y, largura, altura, ...resto } = patch;
        let widgets = prev.widgets.map((w) => (w.id === id ? { ...w, ...resto } : w));
        if (mudaCaixa) {
          widgets = posicionar(widgets, id, {
            x: x ?? atual.x,
            y: y ?? atual.y,
            largura: largura ?? atual.largura,
            altura: altura ?? atual.altura,
          });
        }
        return { ...prev, widgets };
      }, opcoes?.semHistorico);
    },
    [aplicar]
  );

  const setPeriodo = useCallback(
    (p: Periodo) => {
      aplicar((prev) => ({
        ...prev,
        filtros: { ...prev.filtros, periodo: p },
      }));
    },
    [aplicar]
  );

  const desfazer = useCallback(() => {
    setHist((prev) => {
      if (prev.passado.length === 0) return prev;
      return {
        passado: prev.passado.slice(0, -1),
        atual: prev.passado[prev.passado.length - 1],
        futuro: [prev.atual, ...prev.futuro],
      };
    });
  }, []);

  const refazer = useCallback(() => {
    setHist((prev) => {
      if (prev.futuro.length === 0) return prev;
      return {
        passado: [...prev.passado, prev.atual],
        atual: prev.futuro[0],
        futuro: prev.futuro.slice(1),
      };
    });
  }, []);

  const descartar = useCallback(() => {
    setHist(novoHistorico(salvo));
  }, [salvo]);

  const substituir = useCallback((layout: DashboardLayout) => {
    setHist(novoHistorico(layout));
  }, []);

  return {
    draft,
    dirty,
    adicionar,
    remover,
    definirWidgets,
    atualizar,
    setPeriodo,
    desfazer,
    refazer,
    podeDesfazer: hist.passado.length > 0,
    podeRefazer: hist.futuro.length > 0,
    descartar,
    substituir,
  };
}
