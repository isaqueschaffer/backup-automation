import { useRef, useState } from "react";
import type { DragEvent, ReactNode } from "react";
import { DadosDashboard, DashboardLayout, WidgetInstancia } from "./types";
import WidgetFrame from "./WidgetFrame";

interface Props {
  layout: DashboardLayout;
  dados: DadosDashboard | null;
  renderAcoes?: (w: WidgetInstancia) => ReactNode;
  editando?: boolean;
  onMover?: (id: string, alvoId: string, antes: boolean) => void;
}

// Grade de componentes do dashboard com suporte a arrastar e soltar no modo de edição
export default function DashboardCanvas({
  layout,
  dados,
  renderAcoes,
  editando,
  onMover,
}: Props) {
  const widgets = layout?.widgets || [];

  const [dragId, setDragId] = useState<string | null>(null);
  const [dropAt, setDropAt] = useState<{ targetId: string; before: boolean } | null>(null);
  const handleArmed = useRef(false);

  const onDragStart = (e: DragEvent, id: string) => {
    if (!editando || !handleArmed.current) {
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

  return (
    <div className="dash-grid">
      {widgets.map((w) => {
        const isDragging = dragId === w.id;
        const isTarget = dropAt?.targetId === w.id && dragId !== w.id;

        return (
          <div
            className="dash-item"
            key={w.id}
            style={{
              gridColumn: `span ${w.largura}`,
              gridRow: `span ${w.altura}`,
              position: "relative",
              minWidth: 0,
              opacity: isDragging ? 0.4 : 1,
              outline: editando ? "1px dashed var(--border-accent)" : undefined,
              borderRadius: 8,
            }}
            draggable={editando}
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
