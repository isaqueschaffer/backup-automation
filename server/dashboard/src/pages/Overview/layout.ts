import { useCallback, useMemo, useState } from "react";
import { Machine } from "../../api/types";

export type Span = 3 | 4 | 6 | 8 | 12;

export const SPANS: { span: Span; label: string }[] = [
  { span: 3, label: "¼" },
  { span: 4, label: "⅓" },
  { span: 6, label: "½" },
  { span: 8, label: "⅔" },
  { span: 12, label: "Total" },
];

export const DEFAULT_SPAN: Span = 4;

const STORAGE_KEY = "trilan.overview.layout.v1";

interface Stored {
  order: string[];
  hidden: string[];
  spans: Record<string, Span>;
}

function isValidSpan(v: unknown): v is Span {
  return typeof v === "number" && SPANS.some(s => s.span === v);
}

function loadStored(): Stored {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { order: [], hidden: [], spans: {} };
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return { order: [], hidden: [], spans: {} };

    const order = Array.isArray(parsed.order) && parsed.order.every((x: unknown) => typeof x === "string")
      ? parsed.order
      : [];
    const hidden = Array.isArray(parsed.hidden) && parsed.hidden.every((x: unknown) => typeof x === "string")
      ? parsed.hidden
      : [];
    const spans: Record<string, Span> = {};
    if (parsed.spans && typeof parsed.spans === "object") {
      for (const [k, v] of Object.entries(parsed.spans)) {
        if (isValidSpan(v)) spans[k] = v;
      }
    }
    return { order, hidden, spans };
  } catch {
    return { order: [], hidden: [], spans: {} };
  }
}

function saveStored(s: Stored): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // Silencioso
  }
}

// Layout personalizável da Visão Geral (ordem, visibilidade e largura dos cards)
export function useOverviewLayout(machines: Machine[]) {
  const [stored, setStored] = useState<Stored>(() => loadStored());

  const update = useCallback((updater: (prev: Stored) => Stored) => {
    setStored(prev => {
      const next = updater(prev);
      saveStored(next);
      return next;
    });
  }, []);

  const visible = useMemo(() => {
    const machineMap = new Map(machines.map(m => [m.id, m]));
    const hiddenSet = new Set(stored.hidden);
    const result: Machine[] = [];
    const seen = new Set<string>();

    for (const id of stored.order) {
      const m = machineMap.get(id);
      if (m && !hiddenSet.has(id) && !seen.has(id)) {
        result.push(m);
        seen.add(id);
      }
    }

    for (const m of machines) {
      if (!hiddenSet.has(m.id) && !seen.has(m.id)) {
        result.push(m);
        seen.add(m.id);
      }
    }

    return result;
  }, [machines, stored.order, stored.hidden]);

  const isVisible = useCallback((id: string) => {
    return !stored.hidden.includes(id);
  }, [stored.hidden]);

  const spanOf = useCallback((id: string): Span => {
    return stored.spans[id] ?? DEFAULT_SPAN;
  }, [stored.spans]);

  const setSpan = useCallback((id: string, span: Span) => {
    update(prev => ({
      ...prev,
      spans: { ...prev.spans, [id]: span },
    }));
  }, [update]);

  const move = useCallback((dragId: string, targetId: string, before: boolean) => {
    if (!dragId || !targetId || dragId === targetId) return;
    update(prev => {
      const currentIds = visible.map(m => m.id);
      const fromIdx = currentIds.indexOf(dragId);
      const toIdx = currentIds.indexOf(targetId);
      if (fromIdx === -1 || toIdx === -1) return prev;

      const nextOrder = [...currentIds];
      nextOrder.splice(fromIdx, 1);
      const insertIdx = nextOrder.indexOf(targetId);
      if (insertIdx === -1) return prev;
      nextOrder.splice(before ? insertIdx : insertIdx + 1, 0, dragId);

      return {
        ...prev,
        order: nextOrder,
      };
    });
  }, [update, visible]);

  const hide = useCallback((id: string) => {
    update(prev => ({
      ...prev,
      hidden: prev.hidden.includes(id) ? prev.hidden : [...prev.hidden, id],
      order: prev.order.filter(x => x !== id),
    }));
  }, [update]);

  const show = useCallback((id: string) => {
    update(prev => ({
      ...prev,
      hidden: prev.hidden.filter(x => x !== id),
      order: prev.order.filter(x => x !== id).concat(id),
    }));
  }, [update]);

  const reset = useCallback(() => {
    const empty: Stored = { order: [], hidden: [], spans: {} };
    saveStored(empty);
    setStored(empty);
  }, []);

  return {
    visible,
    all: machines,
    isVisible,
    spanOf,
    setSpan,
    move,
    hide,
    show,
    reset,
  };
}
