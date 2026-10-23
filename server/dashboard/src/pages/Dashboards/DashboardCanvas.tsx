import { useEffect, useRef, useState } from "react";
import type { DragEvent, PointerEvent, ReactNode } from "react";
import {
  ALTURA_LINHA_PX,
  DadosDashboard,
  DashboardLayout,
  GAP_GRADE_PX,
  WidgetInstancia,
} from "./types";
import { definicaoDe } from "./widgets/registry";
import { linhasDoConteudo } from "./medirConteudo";
import WidgetFrame from "./WidgetFrame";

interface Props {
  layout: DashboardLayout;
  dados: DadosDashboard | null;
  renderAcoes?: (w: WidgetInstancia) => ReactNode;
  editando?: boolean;
  onMover?: (id: string, alvoId: string, antes: boolean) => void;
  onRedimensionar?: (id: string, tamanho: { largura: number; altura: number }) => void;
  onAjustar?: (id: string, somenteReduzir?: boolean) => void;
}

interface ResizeState {
  id: string;
  axis: "e" | "s" | "se";
  startX: number;
  startY: number;
  startLargura: number;
  startAltura: number;
  passoColuna: number;
  passoLinha: number;
  minL: number;
  minA: number;
  lastL: number;
  lastA: number;
}

// Grade de componentes do dashboard com suporte a arrastar e soltar e redimensionamento por alças
export default function DashboardCanvas({
  layout,
  dados,
  renderAcoes,
  editando,
  onMover,
  onRedimensionar,
  onAjustar,
}: Props) {
  const widgets = layout?.widgets || [];

  const [dragId, setDragId] = useState<string | null>(null);
  const [dropAt, setDropAt] = useState<{ targetId: string; before: boolean } | null>(null);
  const handleArmed = useRef(false);

  const gridRef = useRef<HTMLDivElement>(null);
  const [resizingId, setResizingId] = useState<string | null>(null);
  const resizeRef = useRef<ResizeState | null>(null);

  // Garante a remoção da classe de redimensionamento do body ao desmontar
  useEffect(() => {
    return () => {
      document.body.classList.remove("dash-resizing");
    };
  }, []);

  const onDragStart = (e: DragEvent, id: string) => {
    if (!editando || !handleArmed.current || resizingId) {
      e.preventDefault();
      return;
    }
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", id);
    setDragId(id);
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>, id: string, largura: number) => {
    if (!dragId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const rect = e.currentTarget.getBoundingClientRect();
    let before: boolean;
    if (largura === 12) {
      before = e.clientY < rect.top + rect.height / 2;
    } else {
      before = e.clientX < rect.left + rect.width / 2;
    }
    if (!dropAt || dropAt.targetId !== id || dropAt.before !== before) {
      setDropAt({ targetId: id, before });
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    if (dragId && dropAt && dropAt.targetId && dragId !== dropAt.targetId) {
      onMover?.(dragId, dropAt.targetId, dropAt.before);
    }
    setDragId(null);
    setDropAt(null);
    handleArmed.current = false;
  };

  const onDragEnd = () => {
    setDragId(null);
    setDropAt(null);
    handleArmed.current = false;
  };

  const iniciarRedimensionamento = (
    e: PointerEvent<HTMLDivElement>,
    w: WidgetInstancia,
    axis: "e" | "s" | "se"
  ) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Ignora falha de captura em ambientes sem ponteiro direto
    }

    const gridEl = gridRef.current;
    const larguraGrade = gridEl ? gridEl.getBoundingClientRect().width : 0;
    const passoColuna = (larguraGrade + GAP_GRADE_PX) / 12;
    const passoLinha = ALTURA_LINHA_PX + GAP_GRADE_PX;
    const def = definicaoDe(w.tipo);
    const minL = Math.max(2, def?.larguraMin ?? 2);
    let minA = Math.max(1, def?.alturaMin ?? 1);
    if (!def?.alturaFluida) {
      const item = e.currentTarget.closest<HTMLElement>("[data-widget-id]");
      const fit = item ? linhasDoConteudo(item) : null;
      if (fit !== null) {
        minA = Math.max(1, Math.min(minA, fit));
      }
    }

    resizeRef.current = {
      id: w.id,
      axis,
      startX: e.clientX,
      startY: e.clientY,
      startLargura: w.largura,
      startAltura: w.altura,
      passoColuna: passoColuna > 0 ? passoColuna : 1,
      passoLinha,
      minL,
      minA,
      lastL: w.largura,
      lastA: w.altura,
    };
    setResizingId(w.id);
    document.body.classList.add("dash-resizing");
  };

  const moverRedimensionamento = (e: PointerEvent<HTMLDivElement>, w: WidgetInstancia) => {
    if (!resizeRef.current || resizeRef.current.id !== w.id) return;
    const st = resizeRef.current;
    const dx = e.clientX - st.startX;
    const dy = e.clientY - st.startY;

    let novaLargura = st.startLargura;
    let novaAltura = st.startAltura;

    if (st.axis === "e" || st.axis === "se") {
      const passosX = Math.round(dx / st.passoColuna);
      novaLargura = Math.max(st.minL, Math.min(12, st.startLargura + passosX));
    }
    if (st.axis === "s" || st.axis === "se") {
      const passosY = Math.round(dy / st.passoLinha);
      novaAltura = Math.max(st.minA, Math.min(40, st.startAltura + passosY));
    }

    if (novaLargura !== st.lastL || novaAltura !== st.lastA) {
      st.lastL = novaLargura;
      st.lastA = novaAltura;
      onRedimensionar?.(w.id, { largura: novaLargura, altura: novaAltura });
    }
  };

  const finalizarRedimensionamento = (e: PointerEvent<HTMLDivElement>) => {
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // Ignora falha de liberação de ponteiro
    }
    const id = resizeRef.current?.id;
    resizeRef.current = null;
    setResizingId(null);
    document.body.classList.remove("dash-resizing");

    if (id) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          onAjustar?.(id, true);
        });
      });
    }
  };

  if (widgets.length === 0) {
    return (
      <div
        className="card"
        style={{
          padding: 40,
          textAlign: "center",
          color: "var(--text-muted)",
          fontSize: 14,
        }}
      >
        {editando
          ? "Nenhum componente. Use “Adicionar componente”."
          : "Este dashboard ainda não tem componentes."}
      </div>
    );
  }

  const podeRedimensionar = Boolean(editando && onRedimensionar);

  return (
    <div className="dash-grid" ref={gridRef}>
      {widgets.map((w) => {
        const isDragging = dragId === w.id;
        const isTarget = dropAt?.targetId === w.id && dragId !== w.id;
        const isResizing = resizingId === w.id;

        return (
          <div
            className="dash-item"
            key={w.id}
            data-widget-id={w.id}
            style={{
              gridColumn: `span ${w.largura}`,
              gridRow: `span ${w.altura}`,
              position: "relative",
              minWidth: 0,
              opacity: isDragging ? 0.4 : 1,
              outline: isResizing
                ? "2px solid var(--accent)"
                : editando
                ? "1px dashed var(--border-accent)"
                : undefined,
              borderRadius: 8,
            }}
            draggable={editando && !isResizing}
            onMouseDown={(e) => {
              if (editando) {
                handleArmed.current =
                  (e.target as HTMLElement).closest("[data-drag-handle]") !== null;
              }
            }}
            onDragStart={(e) => onDragStart(e, w.id)}
            onDragOver={(e) => onDragOver(e, w.id, w.largura)}
            onDrop={onDrop}
            onDragEnd={onDragEnd}
          >
            {isTarget &&
              (w.largura === 12 ? (
                <div
                  style={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    top: dropAt.before ? -2 : undefined,
                    bottom: !dropAt.before ? -2 : undefined,
                    height: 3,
                    background: "var(--accent)",
                    borderRadius: 2,
                    zIndex: 10,
                    pointerEvents: "none",
                  }}
                />
              ) : (
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: dropAt.before ? -2 : undefined,
                    right: !dropAt.before ? -2 : undefined,
                    width: 3,
                    background: "var(--accent)",
                    borderRadius: 2,
                    zIndex: 10,
                    pointerEvents: "none",
                  }}
                />
              ))}

            {/* Etiqueta flutuante durante o arrasto de redimensionamento */}
            {isResizing && (
              <div
                style={{
                  position: "absolute",
                  top: 6,
                  right: 6,
                  background: "var(--accent)",
                  color: "#ffffff",
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "2px 6px",
                  borderRadius: 4,
                  pointerEvents: "none",
                  zIndex: 20,
                }}
              >
                {`${w.largura} col × ${w.altura} lin`}
              </div>
            )}

            {/* Alças de redimensionamento em modo de edição */}
            {podeRedimensionar && (
              <>
                {/* Borda direita (largura) */}
                <div
                  className="dash-resize-handle"
                  title="Arraste para alterar a largura"
                  style={{
                    position: "absolute",
                    right: -4,
                    top: 0,
                    width: 10,
                    height: "calc(100% - 16px)",
                    cursor: "ew-resize",
                    zIndex: 5,
                    touchAction: "none",
                  }}
                  onPointerDown={(e) => iniciarRedimensionamento(e, w, "e")}
                  onPointerMove={(e) => moverRedimensionamento(e, w)}
                  onPointerUp={finalizarRedimensionamento}
                  onPointerCancel={finalizarRedimensionamento}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    onAjustar?.(w.id);
                  }}
                />

                {/* Borda inferior (altura) */}
                <div
                  className="dash-resize-handle"
                  title="Arraste para alterar a altura"
                  style={{
                    position: "absolute",
                    bottom: -4,
                    left: 0,
                    height: 10,
                    width: "calc(100% - 16px)",
                    cursor: "ns-resize",
                    zIndex: 5,
                    touchAction: "none",
                  }}
                  onPointerDown={(e) => iniciarRedimensionamento(e, w, "s")}
                  onPointerMove={(e) => moverRedimensionamento(e, w)}
                  onPointerUp={finalizarRedimensionamento}
                  onPointerCancel={finalizarRedimensionamento}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    onAjustar?.(w.id);
                  }}
                />

                {/* Canto inferior direito (largura e altura) */}
                <div
                  className="dash-resize-handle"
                  title="Arraste para redimensionar (ou clique duas vezes para ajustar ao conteúdo)"
                  style={{
                    position: "absolute",
                    right: -2,
                    bottom: -2,
                    width: 16,
                    height: 16,
                    cursor: "nwse-resize",
                    zIndex: 5,
                    touchAction: "none",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                  onPointerDown={(e) => iniciarRedimensionamento(e, w, "se")}
                  onPointerMove={(e) => moverRedimensionamento(e, w)}
                  onPointerUp={finalizarRedimensionamento}
                  onPointerCancel={finalizarRedimensionamento}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    onAjustar?.(w.id);
                  }}
                >
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 12 12"
                    style={{ pointerEvents: "none", flexShrink: 0 }}
                  >
                    <line
                      x1="10"
                      y1="2"
                      x2="2"
                      y2="10"
                      stroke="var(--text-muted)"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    />
                    <line
                      x1="10"
                      y1="5"
                      x2="5"
                      y2="10"
                      stroke="var(--text-muted)"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    />
                    <line
                      x1="10"
                      y1="8"
                      x2="8"
                      y2="10"
                      stroke="var(--text-muted)"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    />
                  </svg>
                </div>
              </>
            )}

            <WidgetFrame
              widget={w}
              dados={dados?.widgets?.[w.id]}
              acoes={renderAcoes?.(w)}
            />
          </div>
        );
      })}
    </div>
  );
}
