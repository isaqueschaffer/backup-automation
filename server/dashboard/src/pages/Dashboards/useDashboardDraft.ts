import { useCallback, useEffect, useMemo, useState } from "react";
import { DashboardLayout, Periodo, WidgetInstancia } from "./types";
import { DefinicaoWidget } from "./widgets/registry";

// Gerencia o estado de rascunho de um dashboard em edição
export function useDashboardDraft(salvo: DashboardLayout) {
  const [draft, setDraft] = useState<DashboardLayout>(salvo);

  useEffect(() => {
    setDraft(salvo);
  }, [salvo]);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(salvo),
    [draft, salvo]
  );

  const adicionar = useCallback((def: DefinicaoWidget): WidgetInstancia => {
    let id = "";
    do {
      id = `${def.tipo}-${Math.random().toString(36).slice(2, 8)}`;
    } while (draft.widgets.some((w) => w.id === id));

    const novo: WidgetInstancia = {
      id,
      tipo: def.tipo,
      titulo: null,
      largura: def.larguraPadrao,
      altura: def.alturaPadrao,
      config: structuredClone(def.configPadrao),
    };

    setDraft((prev) => ({
      ...prev,
      widgets: [...prev.widgets, novo],
    }));

    return novo;
  }, [draft.widgets]);

  const remover = useCallback((id: string) => {
    setDraft((prev) => ({
      ...prev,
      widgets: prev.widgets.filter((w) => w.id !== id),
    }));
  }, []);

  const mover = useCallback((id: string, alvoId: string, antes: boolean) => {
    setDraft((prev) => {
      const fromIdx = prev.widgets.findIndex((w) => w.id === id);
      if (fromIdx === -1) return prev;
      const nextWidgets = [...prev.widgets];
      const [item] = nextWidgets.splice(fromIdx, 1);
      const insertIdx = nextWidgets.findIndex((w) => w.id === alvoId);
      if (insertIdx === -1) return prev;
      nextWidgets.splice(antes ? insertIdx : insertIdx + 1, 0, item);
      return {
        ...prev,
        widgets: nextWidgets,
      };
    });
  }, []);

  const atualizar = useCallback(
    (
      id: string,
      patch: Partial<Pick<WidgetInstancia, "titulo" | "largura" | "altura" | "config">>
    ) => {
      setDraft((prev) => ({
        ...prev,
        widgets: prev.widgets.map((w) => (w.id === id ? { ...w, ...patch } : w)),
      }));
    },
    []
  );

  const setPeriodo = useCallback((p: Periodo) => {
    setDraft((prev) => ({
      ...prev,
      filtros: { ...prev.filtros, periodo: p },
    }));
  }, []);

  const descartar = useCallback(() => {
    setDraft(salvo);
  }, [salvo]);

  const substituir = useCallback((layout: DashboardLayout) => {
    setDraft(layout);
  }, []);

  return {
    draft,
    dirty,
    adicionar,
    remover,
    mover,
    atualizar,
    setPeriodo,
    descartar,
    substituir,
  };
}
