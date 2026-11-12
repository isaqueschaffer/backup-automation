import { ChevronsUpDown, GripVertical, Maximize2, Settings, Trash2 } from "lucide-react";
import { WidgetInstancia } from "./types";

interface Props {
  widget: WidgetInstancia;
  onLarguraTotal: () => void;
  onAjustar: () => void;
  onConfigurar: () => void;
  onRemover: () => void;
}

// Barra de controle de um componente no modo de edição do dashboard
export default function WidgetAcoesEdicao({
  widget,
  onLarguraTotal,
  onAjustar,
  onConfigurar,
  onRemover,
}: Props) {
  return (
    <div
      style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}
      onClick={(e) => e.stopPropagation()}
    >
      <span
        style={{
          fontSize: 10,
          color: "var(--text-muted)",
          userSelect: "none",
          flexShrink: 0,
          marginRight: 2,
        }}
        title={`Tamanho: ${widget.largura} colunas × ${widget.altura} linhas`}
      >
        {widget.largura}×{widget.altura}
      </span>

      <span
        data-drag-handle
        title="Arraste para reordenar"
        style={{
          cursor: "grab",
          display: "inline-flex",
          alignItems: "center",
          padding: "2px 2px",
          color: "var(--text-secondary)",
          flexShrink: 0,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <GripVertical size={15} style={{ flexShrink: 0 }} />
      </span>

      <button
        type="button"
        className="btn-icon"
        title="Ocupar a largura toda"
        style={{ width: 26, height: 26, flexShrink: 0 }}
        onClick={(e) => {
          e.stopPropagation();
          onLarguraTotal();
        }}
      >
        <Maximize2 size={13} style={{ flexShrink: 0 }} />
      </button>

      <button
        type="button"
        className="btn-icon"
        title="Ajustar a altura ao conteúdo (ou dê dois cliques no canto do componente)"
        style={{ width: 26, height: 26, flexShrink: 0 }}
        onClick={(e) => {
          e.stopPropagation();
          onAjustar();
        }}
      >
        <ChevronsUpDown size={14} style={{ flexShrink: 0 }} />
      </button>

      <button
        type="button"
        className="btn-icon"
        title="Configurar componente"
        style={{ width: 26, height: 26, flexShrink: 0 }}
        onClick={(e) => {
          e.stopPropagation();
          onConfigurar();
        }}
      >
        <Settings size={14} style={{ flexShrink: 0 }} />
      </button>

      <button
        type="button"
        className="btn-icon"
        title="Remover componente"
        style={{ width: 26, height: 26, color: "var(--err)", flexShrink: 0 }}
        onClick={(e) => {
          e.stopPropagation();
          onRemover();
        }}
      >
        <Trash2 size={14} style={{ flexShrink: 0 }} />
      </button>
    </div>
  );
}
